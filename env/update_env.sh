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

### GIT
# unstaged (*) and staged (+) changes will be shown next to the branch name
export GIT_PS1_SHOWDIRTYSTATE=1
# If something is stashed, then a '$' will be shown next to the branch name.
export GIT_PS1_SHOWSTASHSTATE=1
# difference between HEAD and its upstream
# "<" indicates you are behind, ">"  indicates you are ahead, "<>" indicates you have diverged and "=" indicates that there is no difference.
export GIT_PS1_SHOWUPSTREAM="auto"
#source /usr/share/git-core/contrib/completion/git-prompt.sh

# export PS1='[\[\033[0;36m\]\u\[\033[0;37m\]@\[\033[0;36m\]\h\[\033[0;37m\]]-[\[\033[0;32m\]\w$(__git_ps1 " (%s)")\[\033[0;37m\]]\n\[\033[0;33m\]\#>>>\[\033[0;37m\]'
export PS1='[\u \W/\[\e[32m\]$(__git_ps1 " (%s)")\[\e[m\]]\$ '

echo Create $USER global git configuration
cp .gitconfig ~/
echo Create $USER .gitignore_global
cp .gitignore_global ~/
