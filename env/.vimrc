let &t_SI = "\<Esc>[5 q"
let &t_SR = "\<Esc>[4 q"
let &t_EI = "\<Esc>[2 q"

set ttimeout
set ttimeoutlen=1
set ttyfast
set ts=2 sw=2
set expandtab


" Install vim-plug if not found
if empty(glob('~/.vim/autoload/plug.vim'))
  silent !curl -fLo ~/.vim/autoload/plug.vim --create-dirs
    \ https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
endif

" Run PlugInstall if there are missing plugins
autocmd VimEnter * if len(filter(values(g:plugs), '!isdirectory(v:val.dir)'))
  \| PlugInstall --sync | source $MYVIMRC
\| endif

let g:vimwiki_list = [{'path':'~/my_data/vimwiki', 'path_html':'~/my_data/vimwiki_html/'}]

nmap <leader>D i<C-R>=strftime("# %a %Y-%m-%d %H:%M")<CR><Esc>
imap <leader>D <C-R>=strftime("# %a %Y-%m-%d %H:%M")<CR>
let g:vimwiki_url_maxsave=0

call plug#begin()
  Plug 'vimwiki/vimwiki'
  Plug 'preservim/nerdtree'
call plug#end()

let &t_SI = "\<Esc>[5 q"
let &t_SR = "\<Esc>[4 q"
let &t_EI = "\<Esc>[2 q"

set ttimeout
set ttimeoutlen=1
set ttyfast
let &t_SI = "\<Esc>[5 q"
let &t_SR = "\<Esc>[4 q"
let &t_EI = "\<Esc>[2 q"

set ttimeout
set ttimeoutlen=1
set ttyfast

source $VIMRUNTIME/mswin.vim
behave mswin

let g:autosave_timer = -1
let g:autosave_backup_dir = expand('~/.vim_autobackups')

" Ensure backup directory exists
if !isdirectory(g:autosave_backup_dir)
  call mkdir(g:autosave_backup_dir, 'p')
endif

function! AutoSaveWithBackup(timer_id) abort
  if &modifiable && !&readonly && &modified && getbufvar('%', '&buftype') == ''
    " Create timestamped backup
    let l:filename = expand('%:p')
    if filereadable(l:filename)
      let l:timestamp = strftime("%Y%m%d_%H%M%S")
      let l:backupname = g:autosave_backup_dir . '/' . substitute(fnamemodify(l:filename, ':t'), '[^a-zA-Z0-9_.]', '_', 'g') . '__' . l:timestamp
      call writefile(readfile(l:filename), l:backupname)
    endif

    " Write the file
    silent! write
    echo "Autosaved and backed up at " . strftime("%H:%M:%S")

    " Clean up backups older than 1 hour (3600 seconds)
    call AutoSaveCleanBackups()
  endif
endfunction

function! AutoSaveCleanBackups() abort
  let l:threshold = localtime() - 86400
  for fname in glob(g:autosave_backup_dir . '/*', 0, 1)
    if getftime(fname) < l:threshold
      call delete(fname)
    endif
  endfor
endfunction

augroup AutoSaveIdle
  autocmd!
  autocmd TextChanged,TextChangedI * call timer_stop(g:autosave_timer) | let g:autosave_timer = timer_start(2000, 'AutoSaveWithBackup')
augroup END



"
"autocmd SwapExists * call AutoDeleteSwap()
"
"function! AutoDeleteSwap()
"  echohl WarningMsg
"  echo "Swap file found. Recovering and deleting swap..."
"  echohl None
"  let v:swapchoice = 'r'  " force recover
"endfunction
"
"autocmd VimEnter * if filereadable(expand('%')) && !filereadable(expand('%:p:h').'/.'.expand('%:t').'.swp') | call DeleteSwapFile() | endif
"
"function! DeleteSwapFile()
"  let swap = expand('%:p:h').'/.'.expand('%:t').'.swp'
"  if filereadable(swap)
"    call delete(swap)
"    echo "Swap file deleted: " . swap
"  endif
"endfunction
