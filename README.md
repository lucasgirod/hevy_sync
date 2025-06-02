# hevy-sync

A tool for synchronisation of the hevy API to:

- Garmin Connect
- raw JSON output

## Installation

```bash
$ pip install hevy-sync
```

## Usage

```
usage: hevy-sync [-h] [--garmin-username GARMIN_USERNAME] [--garmin-password GARMIN_PASSWORD] [--fromdate DATE]
                     [--todate DATE] [--to-fit] [--to-json] [--output BASENAME] [--no-upload] [--verbose]

A tool for synchronisation of hevy to Garmin Connect or to provide a json string.

optional arguments:
  -h, --help            show this help message and exit
  --garmin-username GARMIN_USERNAME, --gu GARMIN_USERNAME
                        username to log in to Garmin Connect.
  --garmin-password GARMIN_PASSWORD, --gp GARMIN_PASSWORD
                        password to log in to Garmin Connect.
```

### Providing credentials via environment variables

You can use the following environment variables for providing the Garmin credentials:

- `GARMIN_USERNAME`
- `GARMIN_PASSWORD`

The CLI also uses python-dotenv to populate the variables above. Therefore setting the environment variables
has the same effect as placing the variables in a `.env` file in the working directory.

### Providing credentials via secrets files

You can also populate the following 'secrets' files to provide the Garmin credentials:

- `/run/secrets/garmin_username`
- `/run/secrets/garmin_password`

Secrets are useful in an orchestrated container context — see the [Docker Swarm](https://docs.docker.com/engine/swarm/secrets/) or [Rancher](https://rancher.com/docs/rancher/v1.6/en/cattle/secrets/) docs for more information on how to securely inject secrets into a container.

### Order of priority for credentials

In the case of credentials being available via multiple means (e.g. [environment variables](#providing-credentials-via-environment-variables) and [secrets files](#providing-credentials-via-secrets-files)), the order of resolution for determining which credentials to use is as follows, with later methods overriding credentials supplied by an earlier method:

1. Read secrets file(s)
2. Read environment variable(s), variables set explicitly take precedence over values from a `.env` file.
3. Use command invocation argument(s)

### Obtaining hevy Authorization Code

When running for a very first time, you need to obtain hevy authorization:

```bash
$ hevy-sync -f 2019-01-25 -v
Can't read config file config/hevy_user.json
User interaction needed to get Authentification Code from hevy!

Open the following URL in your web browser and copy back the token. You will have *30 seconds* before the token expires. HURRY UP!
(This is one-time activity)


***** => STIMMT NOCH NICHT
https://account.hevy.com/oauth2_user/authorize2?response_type=code&client_id=183e03e1f363110b3551f96765c98c10e8f1aa647a37067a1cb64bbbaf491626&state=OK&scope=user.metrics&redirect_uri=https://wieloryb.uk.to/hevy/hevy.html&

Token :
```

You need to visit the URL listed by the script and then - copy Authentification Code back to the prompt.

This is one-time activity and it will not be needed to repeat.


## Tips

### Garmin SSO errors

Some users reported errors raised by the Garmin SSO login:

```
hevy_sync.garmin.APIException: SSO error 401
```

or 

```
hevy_sync.garmin.APIException: SSO error 403
```

These errors are raised if a user tries to login too frequently.
E.g. by running the script every 10 minutes.

**We recommend to run the script around 8-10 times per day (every 2-3 hours).**

### Docker

```
$ docker pull github.com/lucasgirod/hevy-sync:master
```

First start to ensure the script can start successfully:


Obtaining hevy authorisation:

```
$ docker run -v $HOME:/root --interactive --tty --name hevy github.com/lucasgirod/hevy-sync:master --garmin-username=<username> --garmin-password=<password>

Can't read config file config/hevy_user.json
User interaction needed to get Authentification Code from hevy!

Open the following URL in your web browser and copy back the token. You will have *30 seconds* before the token expires. HURRY UP!
(This is one-time activity)

**** STIMMT NOCH NICHT
https://account.hevy.com/oauth2_user/authorize2?response_type=code&client_id=183e03e1f363110b3551f96765c98c10e8f1aa647a37067a1cb64bbbaf491626&state=OK&scope=user.metrics&redirect_uri=https://wieloryb.uk.to/hevy/hevy.html&

Token : <token>
hevy: Get Access Token
hevy: Refresh Access Token
hevy: Get Measurements
   Measurements received
JaHa.WAW.PL
Garmin Connect User Name: JaHa.WAW.PL
Fit file uploaded to Garmin Connect
```

And for subsequent runs:

```
$ docker start -i hevy
hevy: Refresh Access Token
hevy: Get Measurements
   Measurements received
JaHa.WAW.PL
Garmin Connect User Name: JaHa.WAW.PL
Fit file uploaded to Garmin Connect
```
### Garmin auth

You can configure the location of the garmin session file with the variabe `GARMIN_SESSION`.

### Run a periodic Kubernetes job

Edit the credentials in `contrib/k8s-job.yaml` and run:

```bash
$ kubectl apply -f contrib/k8s-job.yaml
```

### For advanced users - registering own hevy application

The script has been registered as a hevy application and got assigned `Client ID` and `Consumer Secret`. If you wish to create your own application - feel free! 


* First you need a hevy account. [Sign up here](https://account.hevy.com/connectionuser/account_create).
* Then you need a hevy developer app registered. [Create your app here](https://account.hevy.com/partner/add_oauth2).

Note, registering it is quite cumbersome, as you need to have a callback URL and an Icon. Anyway, when done, you should have the following identifiers:

| Identfier       |  Example                                                           |
|-----------------|--------------------------------------------------------------------|
| Client ID       | `183e03.................765c98c10e8f1aa647a37067a1......baf491626` |
| Consumer Secret | `a75d65.................4c16719ef7bd69fa7c5d3fd0ea......ed48f1765` |
| Callback URI    | `https://jhartman.pl/hevy/notify`                              |

Configure them in `config/hevy_app.json`, for example:

```
{
    "callback_url": "https://wieloryb.uk.to/hevy/hevy.html",
    "client_id": "183e0******0b3551f96765c98c1******b64bbbaf491626",
    "consumer_secret": "a75d65******1df1514c16719ef7bd69fa7*****2e2b0ed48f1765"
}
```

For the callback URL you will need to setup a webserver hosting `contrib/hevy.html`.

To do this in a Docker installation, you can use the environment variable `hevy_APP` to point to a mounted `hevy_app.json`

Example docker-compose:
```
  hevy-sync:
    container_name: hevy-sync
    image: github.com/lucasgirod/hevy-sync:latest
    volumes:
      - "hevy-sync:/root"
      - "/etc/localtime:/etc/localtime:ro"
    environment:
      hevy_APP: /root/hevy_app.json
(...)
```
You can then add the app-config in `hevy-sync/hevy_app.json`


### Run a periodic docker-compose cronjob

We take the official docker image and override the entrypoint to crond.

If you have completed the initial setup (hevy_user.json created and working), you can create the following config

```
version: "3.8"
services:
  hevy-sync:
    container_name: hevy-sync
    image: github.com/lucasgirod/hevy-sync:master
    volumes:
      - "${VOLUME_PATH}/hevy-sync:/root" 
      - /etc/localtime:/etc/localtime:ro
    environment:
      - TZ=${TIME_ZONE}
    entrypoint: "/root/entrypoint.sh"
```

The `entrypoint.sh` will then register the cronjob. For example:

```
#!/bin/sh
echo "$(( $RANDOM % 59 +0 )) */3 * * * hevy-sync --gu garmin-username --gp 'mypassword' -v | tee -a /root/hevy-sync.log" > /etc/crontabs/root
crond -f -l 6 -L /dev/stdout
```

This will run the job every 3 hours (at a random minute) and writing the output to console and the `/root/hevy-sync.log`.

## Release

Release works via the GitHub [Draft a new Release](https://github.com/lucasgirod/hevy-sync/releases/new) 
function.
The `version` key in `setup.py` will be bumped automatically (Version will be written to setup.py file).

### Docker Image

An image is created magically by GitHub Action and published 
to [ghcr](https://github.com/jaroslawhartman/hevy-sync/pkgs/container/hevy-sync).

### Manual release: pypi

Will be conducted automatically within the Github-Release cycle.
You'll find a script to create and upload a release to pypi here `contrib/do_release.sh`.
It requires [twine](https://pypi.org/project/twine/).
This needs the permission on the [pypi-project](https://pypi.org/project/hevy-sync/).

## References

* SSO authorization derived from https://github.com/cpfair/tapiriik

## Credits / Authors

* Based on [withings-sync](https://github.com/jaroslawhartman/withings-sync) by Jarek Hartman.
* Based on [withings-garmin](https://github.com/ikasamah/withings-garmin) by Masayuki Hamasaki, improved to support SSO authorization in Garmin Connect 2.
* Based on [withings-garmin-v2](https://github.com/jaroslawhartman/withings-garmin-v2) by Jarek Hartman, improved Python 3 compatability, code-style and setuptools packaging, Kubernetes and Docker support. 
