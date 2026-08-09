#!/bin/sh
set -eu

config=/tmp/squid.conf
domains=/tmp/allowed-domains.txt
: > "$domains"
printf '%s' "${ALLOWED_DOMAINS:-}" | tr ',' '\n' | while IFS= read -r domain; do
  clean=$(printf '%s' "$domain" | tr -d '[:space:]')
  [ -n "$clean" ] && printf '%s\n' "$clean" >> "$domains"
done
[ -s "$domains" ] || { echo "ALLOWED_DOMAINS is empty" >&2; exit 2; }

cat > "$config" <<'EOF'
http_port 3128
cache deny all
access_log stdio:/dev/stderr
cache_log /dev/stderr
pid_filename /tmp/squid.pid
coredump_dir /tmp
acl CONNECT method CONNECT
acl SSL_ports port 443
acl Safe_ports port 80 443
acl private_dst dst 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.0.0.0/24 192.168.0.0/16 198.18.0.0/15 224.0.0.0/4 240.0.0.0/4 ::1/128 fc00::/7 fe80::/10
acl allowed dstdomain "/tmp/allowed-domains.txt"
http_access deny private_dst
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow allowed
http_access deny all
EOF

exec squid -N -f "$config"
