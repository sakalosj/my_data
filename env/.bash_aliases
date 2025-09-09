
alias pg="ps -ef|grep -i"
alias hg="history |grep -i"
alias lg="ls -latr |grep -i"

alias va='source ./venv/bin/activate'
alias ve='python3 -m venv ./venv'
alias vd='deactivate'

alias ss='ssh root@172.24.97.70'

s() {
	ssh -t root@$1 bash --rcfile \~/.bashrc_jsakalos -i
  }

si() {
	cd ~/my_data/env/
  scp .bashrc_jsakalos .inputrc root@$1: 
  scp .bash_aliases  root@$1:.bash_aliases_jsakalos
  cd -
	  }

alias pb="cd ~/projects/proxy-b-test-framework; . ./venv/bin/activate"
alias smi="cd ~/my_data/env/; scp .bashrc_jsakalos .inputrc root@172.25.128.185:"
#alias sm="ssh -t root@172.24.97.70 -i ~jsakalos/.ssh/slaves.rsa \"bash --rcfile .bashrc_jsakalos -i\""
#alias sm="ssh -t root@172.24.97.70 -i .ssh/internal/jsakalos-internal-2024-11-21 \"bash --rcfile .bashrc_jsakalos -i\""
alias sm="ssh -t root@172.24.97.70  \"bash --rcfile .bashrc_jsakalos -i\""
alias va=". venv/bin/activate"

alias pg="ps -ef|grep "
alias hg="history |grep "
alias lg="ls -latr |grep "

alias va='source ./venv/bin/activate'
alias ve='python3 -m venv ./venv'
alias vd='deactivate'

#alias sync_test="rsync -azv --delete root@172.24.97.70:/projects/proxy-b-test-framework/test.out/test/ /home/jsakalos/tmp/test"
sync-test(){
HOST="${1:-172.24.97.70}"
rsync -azv --delete root@$HOST:/projects/proxy-b-test-framework/test.out/test/ /home/jsakalos/tmp/test/$HOST
}

alias pg="ps -ef|grep "
alias hg="history |grep "

alias va='source ./venv/bin/activate'
alias ve='python3 -m venv ./venv'
alias vd='deactivate'

#akamai
alias vpn_cs='forticlient vpn connect Akamai_SSL_VPN_SPLIT -w -u jsakalos'
alias vpn_cf='forticlient vpn connect Akamai_SSL_VPN_FULL -w -u jsakalos'
alias vpn_d='forticlient vpn disconnect'
alias vpn_s='forticlient vpn status'
