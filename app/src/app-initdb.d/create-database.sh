#!/bin/bash

# NOTE: file_env, docker_process_sql, _mysql_passfile, logging functions COPIED from 
# https://github.com/docker-library/mysql/blob/master/8.0/docker-entrypoint.sh

# logging functions
mysql_log() {
	local type="$1"; shift
	# accept argument string or stdin
	local text="$*"; if [ "$#" -eq 0 ]; then text="$(cat)"; fi
	local dt; dt="$(date -Iseconds)"
	printf '%s [%s] [Entrypoint]: %s\n' "$dt" "$type" "$text"
}
mysql_note() {
	mysql_log Note "$@"
}
mysql_warn() {
	mysql_log Warn "$@" >&2
}
mysql_error() {
	mysql_log ERROR "$@" >&2
	exit 1
}

# usage: file_env VAR [DEFAULT]
#    ie: file_env 'XYZ_DB_PASSWORD' 'example'
# (will allow for "$XYZ_DB_PASSWORD_FILE" to fill in the value of
#  "$XYZ_DB_PASSWORD" from a file, especially for Docker's secrets feature)
file_env() {
	local var="$1"
	local fileVar="${var}_FILE"
	local def="${2:-}"
	if [ "${!var:-}" ] && [ "${!fileVar:-}" ]; then
		mysql_error "Both $var and $fileVar are set (but are exclusive)"
	fi
	local val="$def"
	if [ "${!var:-}" ]; then
		val="${!var}"
	elif [ "${!fileVar:-}" ]; then
		val="$(< "${!fileVar}")"
	fi
	export "$var"="$val"
	unset "$fileVar"
}

_mysql_passfile() {
	# echo the password to the "file" the client uses
	# the client command will use process substitution to create a file on the fly
	# ie: --defaults-extra-file=<( _mysql_passfile )
    cat <<-EOF
        [client]
        password="`cat /run/secrets/db-password`"
	EOF
    # note use of tab character above
}

# Execute sql script, passed via stdin
#    ie: docker_process_sql <<<'INSERT ...'
#    ie: docker_process_sql <my-file.sql
docker_process_sql() {
    # default mysql but caller can override
	mysql --defaults-extra-file=<( _mysql_passfile) -uroot -hdb --comments --database=mysql "$@"
}

# follow pattern for each application database (https://stackoverflow.com/a/68714439/799921)
file_env APP_PASSWORD
echo "Creating database \`${APP_DATABASE}\`"
mysql_note "Creating database \`${APP_DATABASE}\`"
docker_process_sql <<<"CREATE DATABASE IF NOT EXISTS \`$APP_DATABASE\`;" || exit 1
mysql_note "Creating user ${APP_USER}"
docker_process_sql <<<"CREATE USER IF NOT EXISTS '$APP_USER'@'%' IDENTIFIED BY '$APP_PASSWORD' ;" || exit 1
mysql_note "Giving user ${APP_USER} access to schema ${APP_DATABASE}"
# grant access for user if not done before. see https://dba.stackexchange.com/a/105376
docker_process_sql <<<"GRANT ALL ON \`${APP_DATABASE//_/\\_}\`.* TO '$APP_USER'@'%' ;" || exit 1
# docker_process_sql <<<cat <<-EOF
#     SET @sql_found='SELECT 1 INTO @x';
#     SET @sql_fresh="GRANT ALL ON \`${APP_DATABASE//_/\\_}\`.* TO '$APP_USER'@'%' ;";
#     SELECT COUNT(1) INTO @found_count FROM mysql.user WHERE user='$APP_USER' AND host='%';
#     SET @sql=IF(@found_count=1,@sql_found,@sql_fresh);
#     PREPARE s FROM @sql;
#     EXECUTE s;
#     DEALLOCATE PREPARE s;
# EOF
if [ $? -ne 0 ]; then
  exit 1
fi