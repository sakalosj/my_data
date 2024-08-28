#!/usr/bin/bash

# generate keys
for key in internal deployed;  do echo $key; ssh-keygen -t rsa -b 2048 -C "`whoami`-${key}-`date +%Y-%m-%d`" -f ~/.ssh/${key}/`whoami`-${key}-`date +%Y-%m-%d` -N ""; done

# show fingerprint
for key in internal deployed;  do echo $key; ssh-keygen -l -f  ~/.ssh/${key}/`whoami`-${key}-`date +%Y-%m-%d`; done

ssh-copy-id -i .ssh/internal/`whoami`-internal-`date +%Y-%m-%d` root@172.24.97.70
printf "Upload to:\nhttps://sshkeys.akamai.com/"
printf
printf "Verify at:\nssh kvinternal@ssh-keyrotation.akamai.com\nssh kvdeployed@ssh-keyrotation.akamai.com\n"