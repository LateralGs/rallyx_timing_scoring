#!/bin/sh

script_dir="$(dirname "$(realpath "$0")")";

cd $script_dir/../software

sudo uwsgi ../uwsgi/scoreboard.ini

