# AWS CloudFront route bypass

This VM's provider-bundled Astrill VPN (OpenVPN, tun0) black-holes large
transfers specifically to AWS/CloudFront IP ranges (PMTUD issue - the
tunnel negotiates an MTU too small to sustain them, and ICMP
"fragmentation needed" isn't making it back through). Docker's bridge MTU
setting and TCP MSS clamping on tun0 do not fix this on their own.

Fix: route AWS's published CloudFront ranges via the VM's native interface
(ens33) instead of the VPN, leaving everything else - including all
crawler/Tor traffic - on the VPN as intended.

Installed as:
  /usr/local/sbin/darkweb-aws-bypass.sh   - fetches ip-ranges.amazonaws.com,
                                              applies routes for the
                                              CLOUDFRONT service
  /etc/systemd/system/darkweb-aws-bypass.service  - oneshot runner
  /etc/systemd/system/darkweb-aws-bypass.timer    - runs 2 min after boot,
                                                      then daily (AWS's
                                                      ranges do change)

To reinstall after a rebuild:
    sudo cp darkweb-aws-bypass.sh /usr/local/sbin/
    sudo chmod +x /usr/local/sbin/darkweb-aws-bypass.sh
    sudo cp darkweb-aws-bypass.service darkweb-aws-bypass.timer /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now darkweb-aws-bypass.timer
    sudo systemctl start darkweb-aws-bypass.service
