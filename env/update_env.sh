#!/usr/bin/bash

echo Update root env ...
sudo update_root_env.sh

echo Update $USER bash aliases ...
cat << EOF >> ~/.bash_aliases 

alias pg="ps -ef|grep "
alias hg="history |grep "

alias va='source ./venv/bin/activate'
alias ve='python3 -m venv ./venv'
alias vd='deactivate'
EOF


echo Update $USER .vimrc
cat << EOF >> ~/.vimrc
let &t_SI = "\<Esc>[5 q"
let &t_SR = "\<Esc>[4 q"
let &t_EI = "\<Esc>[2 q"

set ttimeout
set ttimeoutlen=1
set ttyfast

EOF

echo Create $USER global git configuration
cp .gitconfig ~/
echo Create $USER .gitignore_global
cp .gitignore_global ~/
