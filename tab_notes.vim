setlocal filetype=markdown
setlocal wrap linebreak
augroup herdr_tab_notes
    autocmd!
    autocmd TextChanged,TextChangedI,InsertLeave,FocusLost,BufLeave <buffer> silent update
augroup END
