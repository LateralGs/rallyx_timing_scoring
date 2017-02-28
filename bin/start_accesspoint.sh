#!/bin/bash

if [ -z $1 ]
then
iface=`ls /sys/class/net | grep wlp0s26u | head -n1`
else
iface=$1
fi

echo $iface

create_ap -n --redirect-to-localhost --isolate-clients -g 10.10.10.10 "$iface" nwra_scoring_2

