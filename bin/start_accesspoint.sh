#!/bin/bash

if [ -z $1 ]
then
iface=`ls /sys/class/net | grep wlp0s26u | head -n1`
else
iface=$1
fi

if [ -z $2 ]
then
ssid=`hostname`
else
ssid=$2
fi

echo $iface
echo $ssid

sudo create_ap -n --redirect-to-localhost --isolate-clients -g 10.10.10.10 "$iface" "$ssid"

