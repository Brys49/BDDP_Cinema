# Cinema Reservation App

## Krzysztof Bryszak 156052

### Description:

Cinema Reservation App is a console app that allows you to make, update and view reservations for different movies and users. It can also run 3 stress tests to verify system performance.

### Requirements:
- Python 3.9+
- cassandra-driver
- Docker
- Docker-compose

### How to run:
- download the project from Github repo
- run ``` docker-compose up -d ``` in project directory and wait for the nodes to start
- run ``` python project.py ``` (if you can't connect to a node, check and update node IP address in the project.py file)
- to shut down exit the program and run ``` docker-compose down ```
