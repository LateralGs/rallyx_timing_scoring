#!/bin/sh
script_dir = "$(dirname "$(realpath "$0")")";
cd $script_dir/software
uwsgi ../uwsgi/scoring_admin.ini

