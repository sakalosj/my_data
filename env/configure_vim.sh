#!/usr/bin/bash

echo Download vim-plug
curl -fLo ~/.vim/autoload/plug.vim --create-dirs \
    https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim

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

let data_dir = has('nvim') ? stdpath('data') . '/site' : '~/.vim'
if empty(glob(data_dir . '/autoload/plug.vim'))
  silent execute '!curl -fLo '.data_dir.'/autoload/plug.vim --create-dirs  https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim'
  autocmd VimEnter * PlugInstall --sync | source $MYVIMRC
endif

call plug#begin()
Plug 'tpope/vim-sensible'
call plug#end()

EOF

echo Create $USER global git configuration
cp .gitconfig ~/
echo Create $USER .gitignore_global
cp .gitignore_global ~/
