#!/usr/bin/bash

echo Update $USER inputrc
cat << EOF >> /etc/inputrc
set show-mode-in-prompt on
set vi-cmd-mode-string \1\e[2 q\2
set vi-ins-mode-string \1\e[6 q\2
EOF


echo Update $USER bashrc
cat << EOF >> /etc/bash.bashrc
export EDITOR=vim
export VISUAL=vim
set -o vi

export PS1="[\u:\w]\\$ "
export PROMPT_COMMAND="history -a; history -c; history -r; $PROMPT_COMMAND"

alias pg='ps -ef|grep -i'
alias hg='history|grep -i'
EOF
