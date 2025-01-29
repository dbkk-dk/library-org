from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import func
from sqlalchemy import or_, asc, desc
from sqlalchemy.exc import IntegrityError

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, validators

import requests
import json

import configparser
import os
from pathlib import Path
import re
import sys
import pprint

try:
    p = Path(__file__).absolute()
except NameError:
    # we're in repl
    p = Path.cwd() / 'controller.py'
CONFIG_FILE = "library.cfg"
PROJECT_ROOT = p.parent
# library.cfg is either in this dir(PROJECT_ROOT) or parent
for fpath in [p.parents[1], PROJECT_ROOT]:
    CONFIG_PATH = fpath / CONFIG_FILE
    if CONFIG_PATH.is_file():
        break
else:
    sys.exit(
        f"{CONFIG_FILE} was not found in src or parent dir. Remember to create it from 'LIBRARY.cfg_EXAMPLE' ")

CONFIG = configparser.ConfigParser()
CONFIG.read(CONFIG_PATH)

# Configuration Secrets
APP_SECRET_KEY = CONFIG.get("secrets", "APP_SECRET_KEY")
WTF_CSRF_SECRET_KEY = CONFIG.get("secrets", "WTF_CSRF_SECRET_KEY")
NEW_ISBN_SUBMIT_SECRET = CONFIG.get("secrets", "NEW_ISBN_SUBMIT_SECRET")
NEW_LOCATION_SUBMIT_SECRET = CONFIG.get("secrets", "NEW_LOCATION_SUBMIT_SECRET")
RECAPTCHA_PUBLIC_KEY = CONFIG.get("secrets", "RECAPTCHA_PUBLIC_KEY")
RECAPTCHA_PRIVATE_KEY = CONFIG.get("secrets", "RECAPTCHA_PRIVATE_KEY")
USER = {"username": CONFIG.get("secrets", "USERNAME"),
        "password": CONFIG.get("secrets", "PASSWORD")}

db_name = "books.sqlite"
DB_DIR = "database"
sqlite_db = "sqlite:////" + os.path.join(PROJECT_ROOT, "database", db_name)

# haven't used this in the templates, currently using exact path on a few files.
# not even sure if this django style approach works with flask
STATIC_DIR = "static"

app = Flask(__name__)

app.secret_key = APP_SECRET_KEY

# flask will reload itself on changes when debug is True
# flask can execute arbitrary code if you set this True
app.debug = True

# sqlalchemy configuration
app.config["SQLALCHEMY_DATABASE_URI"] = sqlite_db
db = SQLAlchemy(app)

PAGINATE_BY_HOWMANY = 20

# == recaptcha ==
# recaptcha disabled - it is ready to be implemented now
# RECAPTCHA_PARAMETERS = {'hl': 'zh', 'render': 'explicit'}
# RECAPTCHA_DATA_ATTRS = {'theme': 'dark'}
# app.config['RECAPTCHA_USE_SSL'] = False


class Location(db.Model):
    """Locations have a shortname and a pkey ID.

    Books are linked to location by ForeignKey using the ID (pkey).
    """

    id = db.Column(db.Integer, primary_key=True)
    label_name = db.Column(db.String(20), unique=True)
    full_name = db.Column(db.String(100), unique=False)
    # books = db.relationship("Book", backref="person", lazy="dynamic")

    def __init__(self, label_name, full_name):
        self.label_name = label_name
        self.full_name = full_name

    def __repr__(self):
        return "<Location Label: >".format(self.label_name)


class Book(db.Model):
    """Build a model based on the available fields in the openlibrary.org API.

    Notes:
        authors - will be stored as a long string, openlibrary delivers it as a list of objects.

    Additional info:
        curl 'https://openlibrary.org/api/books?bibkeys=ISBN:9780980200447&jscmd=data&format=json'
        using jscmd=data yields less info but is more stable
        using jscmd=details will give us book cover thumbnail, preview url, table of contents, and more

    Enhancements:
        use jscmd=details to get cover thumbnail... this could be a key piece of the template
    """

    id = db.Column(db.Integer, primary_key=True)
    isbn = db.Column(db.String(20), unique=False)
    olid = db.Column(db.String(20), unique=False)
    lccn = db.Column(db.String(20), unique=False)
    title = db.Column(db.String(200), unique=False)
    authors = db.Column(db.String(200), unique=False)
    publish_date = db.Column(db.String(30), unique=False)
    number_of_pages = db.Column(db.String(10), unique=False)
    subjects = db.Column(db.String(5000), unique=False)
    openlibrary_medcover_url = db.Column(db.String(500), unique=False)
    openlibrary_preview_url = db.Column(db.String(500), unique=False)
    dewey_decimal_class = db.Column(db.String(50), unique=False)
    location = db.Column(
        db.Integer, db.ForeignKey("location.id"), default=None, nullable=True
    )

    def __init__(
        self,
        isbn,
        olid,
        lccn,
        title,
        number_of_pages,
        publish_date,
        authors,
        subjects,
        openlibrary_medcover_url,
        openlibrary_preview_url,
        dewey_decimal_class,
        location,
    ):

        self.isbn = isbn
        self.olid = olid
        self.lccn = lccn
        self.title = title
        self.authors = authors
        self.publish_date = publish_date
        self.number_of_pages = number_of_pages
        self.subjects = subjects
        self.openlibrary_medcover_url = openlibrary_medcover_url
        self.openlibrary_preview_url = openlibrary_preview_url
        self.dewey_decimal_class = dewey_decimal_class
        self.location = location

    def __repr__(self):
        return "<Title: >".format(self.title)


class LocationForm(FlaskForm):
    # attach form.location.choices = location_options after instantiation!!
    # http://wtforms.readthedocs.io/en/latest/fields.html#wtforms.fields.SelectField
    location = SelectField(coerce=int)


class NewLocationForm(FlaskForm):
    # These constraints are temporary and can change to support the labelling system.
    new_location = StringField("label_name", [validators.Length(min=5, max=10)])
    location_entry_secret = StringField(
        "location_entry_secret", validators=[validators.Length(min=1, max=200)]
    )


@app.route("/index")
@app.route("/")
def home():
    return redirect(url_for("index", page=1))


# Function to fetch book details using an ISBN
def fetch_book_details(isbn):
    google_books_url = f'https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}'
    open_library_url = f'https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&jscmd=data'

    # Fetch data from Open Library
    open_library_response = requests.get(open_library_url)
    open_library_data = open_library_response.json() if open_library_response.status_code == 200 else {}
    # pprint.pprint((open_library_data))

    book_details = {}
    # Open Library data
    if f'ISBN:{isbn}' in open_library_data:
        open_library_info = open_library_data[f'ISBN:{isbn}']

        # Extract title and subtitle from Open Library (if available)
        open_library_title = open_library_info.get('title', '')
        open_library_subtitle = open_library_info.get('subtitle', '')
        # Combine title and subtitle (if subtitle exists)
        if open_library_subtitle:
            book_details['title'] = f"{open_library_title} - {open_library_subtitle}"
        else:
            book_details['title'] = open_library_title

        book_details['authors'] = [author['name'] for author in open_library_info.get('authors', [])]
        book_details['publishedDate'] = open_library_info.get('publish_date', '')
        book_details['description'] = open_library_info.get('description', '')
        # Extract and store only the names of the subjects
        book_details['subjects'] = [subject['name'] for subject in open_library_info.get('subjects', [])]
        book_details['number_of_pages'] = open_library_info.get('number_of_pages', '')
        book_details['preview_link'] = f"https://openlibrary.org{open_library_info.get('key', '')}"  # Link to borrow or more info
        book_details['thumbnail'] = open_library_info.get('cover', {}).get('medium', '')

    # If no Open Library data, try Google Books
    if not book_details.get('title'):
        google_books_response = requests.get(google_books_url)
        google_books_data = google_books_response.json() if google_books_response.status_code == 200 else {}
        # pprint.pprint((google_books_data))

        if 'items' in google_books_data:
            google_book = google_books_data['items'][0]
            google_info = google_book.get('volumeInfo', {})

            google_title = google_info.get('title', '')
            google_subtitle = google_info.get('subtitle', '')
            # Combine title and subtitle (if subtitle exists)
            if google_subtitle:
                book_details['title'] = f"{google_title} - {google_subtitle}"
            else:
                book_details['title'] = google_title

            book_details['authors'] = google_info.get('authors', [])
            book_details['publishedDate'] = google_info.get('publishedDate', '')
            book_details['description'] = google_info.get('description', '')
            book_details['thumbnail'] = google_info.get('imageLinks', {}).get('thumbnail', '')
            book_details['subjetcs'] = google_info.get('categories', [])
            book_details['number_of_pages'] = google_info.get('pageCount', '')
            book_details['preview_link'] = google_info.get('previewLink', '')

    # Return the combined details
    return book_details


@app.route("/add_book", methods=["GET", "POST"])
def add_book():
    """Add a new book to the system by entering ISBN or manually filling fields."""

    # Fetch locations from the database (or use predefined list if necessary)
    locations = Location.query.order_by("label_name").all()
    location_choices = [(l.id, f"{l.label_name}, {l.full_name}") for l in locations]  # Populate choices dynamically
    location_form = LocationForm()

    # Pre-fill location choices
    location_form.location.choices = location_choices + [(-1, u"-- Add the correct location --")]

    if request.method == "POST":
        if "search_isbn" in request.form:  # Handle ISBN search
            isbn = request.form.get("isbn")
            if not check_isbn(isbn):
                return "Invalid ISBN. Please enter a valid 10 or 13-digit ISBN."

            # Fetch book details from both Google Books and OpenLibrary
            book_data = fetch_book_details(isbn)
            if not book_data:
                return "Book not found. Please check the ISBN or enter details manually."

            return render_template(
                "add_book.html",
                isbn=isbn,
                title=book_data.get("title", ""),
                authors=", ".join(book_data.get("authors", [])),
                year=book_data.get("publishedDate", ""),
                description=book_data.get("description", ""),
                thumbnail_url=book_data.get("thumbnail", ""),
                subjects=", ".join(book_data.get("subjects", [])),
                number_of_pages=book_data.get("number_of_pages", ""),
                openlibrary_preview_url=book_data.get("preview_link", ""),
                location_form=location_form,  # Pass location form with choices
            )

        elif "submit_book" in request.form:  # Handle form submission
           # Check if the book already exists by ISBN
            isbn = request.form.get("isbn")
            existing_book = Book.query.filter_by(isbn=isbn).first()
            if existing_book:
                flash("This book already exists in the system. Redirecting to its details page.", "info")
                return redirect(url_for("detail", id=existing_book.id))  # Redirect to the existing book's detail page

            # Handle location selection
            location_id = request.form.get("location")
            location_id = int(location_id) if location_id and location_id != "-1" else None
            title=request.form.get("title", "").strip()
            authors=request.form.get("authors", "").strip()
            if not title or not authors or not location_id:
                flash("Title, Authors, and Location are required fields!", "danger")
                return redirect(url_for('add_book'))

            # Save the book to the database
            new_book = Book(
                isbn=request.form.get("isbn", "").strip(),
                title=title,
                authors=authors,
                publish_date=request.form.get("year", "").strip(),
                subjects=request.form.get("subjects", "").strip(),
                openlibrary_medcover_url=request.form.get("thumbnail_url", "").strip(),
                openlibrary_preview_url=request.form.get("preview_link", "").strip(),
                olid=request.form.get("openlibrary_link", "").strip(),
                number_of_pages=request.form.get("number_of_pages", "").strip(),
                dewey_decimal_class="",  # Not used
                lccn="", # not used
                location=location_id,
            )
            db.session.add(new_book)
            db.session.commit()
            return redirect(url_for("detail", id=new_book.id))

    # locations = LibraryLocation.query.all()  # Fetch available library locations
    return render_template("add_book.html", location_form=location_form)

@app.route("/edit_book/<int:id>", methods=["GET", "POST"])
def edit_book(id):
    """Edit an existing book's details with an ISBN search option."""
    book = Book.query.get(id)

    if book is None:
        flash(f"Book with ID {id} does not exist.", "danger")
        return redirect(url_for("index"))

    # Fetch available locations
    locations = Location.query.order_by("label_name").all()
    location_choices = [(l.id, f"{l.label_name}, {l.full_name}") for l in locations]

    if request.method == "POST":
        if "search_isbn" in request.form:
            # Fetch book details by ISBN and overwrite fields only if they have meaningful data
            isbn = str(request.form.get("isbn", "")).strip()
            if not check_isbn(isbn):
                flash("Invalid ISBN. Please enter a valid 10 or 13-digit ISBN.", "danger")
                return redirect(url_for("edit_book", id=book.id))

            book_data = fetch_book_details(isbn)
            if not book_data:
                flash("Book not found. Please enter details manually.", "warning")
                return redirect(url_for("edit_book", id=book.id))

            # Set ISBN, in case it was missing in the DB
            book_data["isbn"] = isbn
            # Only overwrite fields if they contain meaningful data
            if book_data.get("title"): book.title = book_data["title"]
            if book_data.get("authors"): book.authors = ", ".join(book_data.get("authors", []))
            if book_data.get("publish_date"): book.publish_date = book_data["publish_date"]
            if book_data.get("subjects"): book.subjects = ", ".join(book_data.get("subjects", []))
            if book_data.get("thumbnail"): book.openlibrary_medcover_url = book_data["thumbnail"]
            if book_data.get("preview_link"): book.openlibrary_preview_url = book_data["preview_link"]
            if book_data.get("number_of_pages"): book.number_of_pages = book_data["number_of_pages"]

            flash("Book details updated from ISBN search!", "info")
            return render_template(
                "edit_book.html",
                book=book,
                locations=location_choices
            )

        elif "submit_book" in request.form:
            # Ensure ISBN is unique (excluding the current book)
            isbn = str(request.form.get("isbn", "")).strip()
            existing_book = Book.query.filter(Book.isbn == isbn, Book.id != book.id).first()
            if existing_book:
                flash("A book with this ISBN already exists.", "danger")
                return redirect(url_for("detail", id=existing_book.id))

            # Update book details from form
            book.isbn = isbn
            book.title = request.form.get("title", "").strip()
            book.authors = request.form.get("authors", "").strip()
            book.publish_date = request.form.get("year", "").strip()
            book.subjects = request.form.get("description", "").strip()
            book.openlibrary_medcover_url = request.form.get("thumbnail_url", "").strip()
            book.openlibrary_preview_url = request.form.get("openlibrary_preview_url", "").strip()
            book.number_of_pages = request.form.get("number_of_pages", "").strip()

            # Handle location selection
            location_id = request.form.get("location")
            book.location = int(location_id) if location_id and location_id != "-1" else None

            # Commit the changes
            db.session.commit()
            flash("Book details updated successfully!", "success")
            return redirect(url_for("detail", id=book.id))

    return render_template(
        "edit_book.html",
        book=book,
        locations=location_choices
    )


@app.route("/delete_book/<int:id>", methods=["POST"])
def delete_book(id):
    """Delete a book from the database."""
    book = Book.query.get(id)

    if book is None:
        flash(f"Book with ID {id} does not exist.", "danger")
        return redirect(url_for("index"))

    db.session.delete(book)
    db.session.commit()

    flash("Book deleted successfully!", "success")
    return redirect(url_for("index", page=1))

@app.route("/new_location", methods=["GET", "POST"])
def new_location(new_location=None, new_location_submit_secret=None):
    """Register a new location"""

    new_location_form = NewLocationForm(request.form)

    if request.method == "GET":
        pass

    if request.method == "POST" and new_location_form.validate():

        if new_location_form.location_entry_secret.data != NEW_LOCATION_SUBMIT_SECRET:
            return "Bad Secret, try again. This page will be more friendly later :-)"

        new_location = new_location_form.new_location.data
        location_exists = Location.query.filter_by(label_name=new_location).first()

        if location_exists:
            return "This location already exists! Try again. Friendly response later."
        else:
            # label_name, full_name
            newlocationdata = Location(new_location, "")
            db.session.add(newlocationdata)
            db.session.commit()
            return "Congratulations, {} has been added to your locations. Make this response nice.".format(
                new_location
            )

    return render_template(
        "new_location.html",
        new_location_form=new_location_form,
        new_location=new_location,
        new_location_submit_secret=new_location_submit_secret,
    )


@app.route("/detail/<int:id>", methods=["GET", "POST"])
def detail(id=1):
    """Show an individual work"""

    newbookflash = session.get("newbookflash", False)
    session.pop("newbookflash", None)
    book = Book.query.get(id)

    if book is None:
        return f"<h1>book id {id} does not exist</h1>"

    # Fetch available locations
    locations = Location.query.order_by("label_name").all()

    # Set the location to be displayed
    location_display = None
    if book.location:
        location_display = next((l for l in locations if l.id == book.location), None)

    return render_template(
        "detail.html", book=book, newbookflash=newbookflash, location_display=location_display
    )


@app.route("/explore")
def explore():
    """Return index.html for all books with randomized sorting."""

    books = db.session.query(Book, Location).\
        join(Location, Book.location == Location.id).filter().order_by(func.random())

    return render_template("index.html",
                           books=books.paginate(page=1, per_page=len(books.all()), error_out=False),
                           s="", sort_by="")


@app.route("/index/<int:page>", methods=["GET", "POST"])
def index(page=1):
    """Show an index of books, provide some basic searchability."""

    if request.method == "POST":
        s = request.form["search"]
        return redirect(url_for("index", page=1, s=s))

    # Get the search term and number of items per page from the request
    s = request.args.get("s")
    per_page = request.args.get("per_page", PAGINATE_BY_HOWMANY, type=int)
    sort_by = request.args.get("sort_by", "title")  # Default sort by title
    sort_order = request.args.get("sort_order", "asc")  # Default order is ascending

    # Set sorting direction (ascending or descending)
    if sort_order == "asc":
        sort_direction = asc
    else:
        sort_direction = desc

    # Create the query to select books
    query = db.session.query(Book, Location).join(Location, Book.location == Location.id)
   # Apply filtering if a search term is provided
    if s:
        query = query.filter(
            or_(
                Book.title.contains(s),
                Book.authors.contains(s),
                Book.subjects.contains(s),
                Book.isbn.contains(s),
            )
        )

    # Apply sorting based on the 'sort_by' and 'sort_order' parameters
    query = query.order_by(sort_direction(getattr(Book, sort_by)))

    # Execute the pagination
    books = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template("index.html", books=books, s=s, sort_by=sort_by, sort_order=sort_order, per_page=per_page)


@app.route('/login', methods = ['POST', 'GET'])
def login():
    if(request.method == 'POST'):
        username = request.form.get('username')
        password = request.form.get('password')
        if username == USER['username'] and password == USER['password']:
            session['logged_in'] = True
            # session['user'] = username
            return redirect('/index')

        return "<h1>Wrong username or password</h1>"    #if the username or password does not matches

    return render_template("login.html")


@app.route("/logout")
def logout():
    session['logged_in'] = False
    return redirect('/index')

def check_isbn(isbn:str|None) -> bool:
    """Check we have a ISBN

    https://stackoverflow.com/a/4047709
    https://rosettacode.org/wiki/ISBN13_check_digit#Python
    """

    if isbn is None:
        return False

    isbn = isbn.replace("-", "").replace(" ", "").upper();
    if len(isbn) == 10:
        match = re.search(r'^(\d{9})(\d|X)$', isbn)
        if not match:
            return False

        digits = match.group(1)
        check_digit = 10 if match.group(2) == 'X' else int(match.group(2))

        result = sum((i + 1) * int(digit) for i, digit in enumerate(digits))
        return (result % 11) == check_digit
    else:
        result = (sum(int(ch) for ch in isbn[::2]) + sum(int(ch) * 3 for ch in isbn[1::2]))
        return result % 10 == 0


if __name__ == "__main__":
    # flask can execute arbitrary python if you do this.
    # app.run(host='0.0.0.0') # listens on all public IPs.

    app.run()
