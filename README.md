

## Project Status

### Missing features
- upload files(pdf) which then can be found from the `index` page,

### bugs
- Updating a book without ISBN result in an error
- creating a new book without ISBN result in an error

## docker
Remember to copy `library.cfg_EXAMPLE` to `library.cfg` and change env variables as needed.

NB, just a note about docker:
- image is the instructions for how to
- build and run a container

Steps to build a tagged image and run it
``` sh
docker build -t library .
docker run -d --restart=always --name=dbkk-library -p 80:5000 -e FLASK_APP=controller.py library
```

With `--restart=always` there is no need for a [systemd-service file](https://stackoverflow.com/a/30450350).

When pullling new code the image have to rebuild and the container deleted(stooped and recreated)
``` sh
docker build -t library .
docker rm dbkk-library
docker run -d --restart=always --name=dbkk-library -p 80:5000 -e FLASK_APP=controller.py library
```

The old image will still exist locally, but `docker images` will show <none> as its name or tag. `docker system prune` will clean up the old image.

If the container just runs a one-off test, you might delete the old container before building a new image, or use the `docker run --rm` option to have the container delete itself. add `--entrypoint bash` to get a shell if the app is crashing and the container exists, which prevents `docker exec bash` from working.

``` sh
docker run --rm -it -e FLASK_APP=controller.py -e FLASK_DEBUG=1 -p 5000:5000 library
docker run --rm -it -e FLASK_APP=controller.py -e FLASK_DEBUG=1 -p 5000:5000 --entrypoint bash library
```

`docker run` creates and start a new container. `docker start` start an already existing container.

## docker-compose

`docker-compose` mounts the code into the container so code-changes are automatically seen by the app.
``` sh
docker-compose up -d  # or for production
docker-compose up -d -f docker-compose.prod.yml
```

go to [localhost:5000] (http://localhost:5000) in the browser


## Amazon ec2 instance

``` sh
ssh ec2-user@ec2-ip-address-dns-name-here

sudo yum install docker git
sudo systemctl enable docker.service
sudo systemctl start docker.service

# add user to docker group
sudo usermod -a -G docker ec2-user
id ec2-user
# logout

git clone https://github.com/dbkk-dk/library-org.git

```

