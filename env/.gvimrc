colorscheme desert
"set guioptions-=m  "menu bar
set guioptions-=T  "toolbar
set guioptions-=r  "scrollbar
set lines=999 columns=999




"autocmd VimEnter * if argc() && v:swapname != '' | call DeleteSwapfile(v:swapname) | endif

"function! DeleteSwapfile(swapname)
"  if filereadable(a:swapname)
"    call delete(a:swapname)
"    echom "Deleted swap file after recovery: " . a:swapname
"  endif
"endfunction


set updatetime=500 
au CursorHold,CursorHoldI <buffer> if &readonly == 0 && filereadable(bufname('%')) | silent write | endif
