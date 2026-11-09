if [[ ${HERDR_ENV:-} == 1 ]]; then
    herdr_vim_notes_script="${${(%):-%x}:A:h}/tab_notes.py"
    if python3 "$herdr_vim_notes_script" should-resume; then
        exec python3 "$herdr_vim_notes_script" edit
    fi
    unset herdr_vim_notes_script
fi
