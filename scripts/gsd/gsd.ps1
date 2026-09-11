param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$GsdArgs
)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$scriptDir\gsd.py" @GsdArgs
