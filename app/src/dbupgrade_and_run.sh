#!/bin/sh

# NOTE: file end of line characters must be LF, not CRLF (see https://stackoverflow.com/a/58220487/799921)

# create database if necessary
while ! ./app-initdb.d/create-database.sh
do
    sleep 5
done

# initial volume create may cause flask db upgrade to fail
while ! flask db upgrade
do
    sleep 5
done
exec "$@"
