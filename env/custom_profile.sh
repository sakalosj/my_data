set -o vi

export PS1="[\u:\w]\\$ "
export PROMPT_COMMAND="history -a; history -c; history -r; $PROMPT_COMMAND"

