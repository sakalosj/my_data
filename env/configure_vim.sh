#!/usr/bin/bash

if [ -f ~/.vim/autoload/plug.vim ]; then
	echo vim-plug already present
else
	echo Download vim-plug
	curl -fLo ~/.vim/autoload/plug.vim --create-dirs \
    https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
fi


echo Update $USER .vimrc
cp .vimrc ~/.vimrc

echo Update $USER .gvimrc
cat << EOF >> ~/.gvimrc
colorscheme desert
set guioptions-=m  "menu bar
set guioptions-=T  "toolbar
set guioptions-=r  "scrollbar
set lines=999 columns=999

EOF

