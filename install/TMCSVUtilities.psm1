# adapted from https://stackoverflow.com/a/76723749
function Import-Env {
    [CmdletBinding(SupportsShouldProcess)]
    [Alias('dotenv')]
    param(
        [ValidateNotNullOrEmpty()]
        [String] $Path = '.env',

        # Determines whether variables are environment variables or normal
        [ValidateSet('Environment', 'Regular')]
        [String] $Type = 'Environment'
    )
    $Env = Get-Content -raw $Path | ConvertFrom-StringData
    $Env.GetEnumerator() | Foreach-Object {
        $Name, $Value = $_.Name, $_.Value
        if ($PSCmdlet.ShouldProcess($Name, "Importing $Type Variable")) {
            switch ($Type) {
                'Environment' { Set-Content -Path env:$Name -Value $Value }
                'Regular' { Set-Variable -Name $Name -Value $Value -Scope Script }
            }
        }
    }
}

Export-ModuleMember -Function Import-Env