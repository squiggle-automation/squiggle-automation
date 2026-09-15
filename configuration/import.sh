#!/bin/sh

set -eu

BASE_PATH="$(dirname $(dirname "$(readlink -f $0)"))"
CLI="$BASE_PATH/cli/cli.py"

# import all definitions
$CLI import workerprofiles ./workerprofiles
$CLI import entitytypes ./entitytypes
$CLI import configoptions ./configoptions
$CLI import containers ./containers
$CLI import executors ./executors

# set default config
$CLI config set nmap_ping false
$CLI config set dns_resolver 8.8.8.8
$CLI config set nmap_no_dns true
$CLI config set nmap_ping false
$CLI config set nmap_scan_mode syn
$CLI config set nmap_service_detection true
$CLI config set nmap_script_scan false
$CLI config set nmap_timing 4

# set executor specific config
$CLI config set --executor portscan-tcp-top100 nmap_top_ports 100

$CLI config set --executor dns-resolve dnsx_mode forward

$CLI config set --executor dns-reverse dnsx_mode reverse
