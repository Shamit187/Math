# Adds a persistent Windows Firewall inbound rule allowing TCP 8765
# (the Slow Books server) ONLY from the Tailscale network ranges.
# Run elevated. Idempotent — removes any prior copy of the rule first.

$ErrorActionPreference = 'Stop'
$name = 'Slow Books TTS (Tailscale 8765)'
$log  = 'C:\CodeFile\Math\tools\.fw_result.txt'

try {
    Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule `
        -DisplayName $name `
        -Description 'Allow inbound TTS/Flask server (port 8765) from the Tailscale tailnet only.' `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Protocol TCP `
        -LocalPort 8765 `
        -RemoteAddress @('100.64.0.0/10', 'fd7a:115c:a1e0::/48') `
        -Profile Any | Out-Null

    $rule = Get-NetFirewallRule -DisplayName $name
    $pf   = $rule | Get-NetFirewallPortFilter
    $af   = $rule | Get-NetFirewallAddressFilter
    "OK    : rule created"                         | Out-File $log -Encoding utf8
    "Name  : $($rule.DisplayName)"                 | Out-File $log -Encoding utf8 -Append
    "State : Enabled=$($rule.Enabled) Action=$($rule.Action) Dir=$($rule.Direction)" | Out-File $log -Encoding utf8 -Append
    "Port  : $($pf.Protocol) $($pf.LocalPort)"     | Out-File $log -Encoding utf8 -Append
    "From  : $($af.RemoteAddress -join ', ')"      | Out-File $log -Encoding utf8 -Append
}
catch {
    "ERROR : $($_.Exception.Message)" | Out-File $log -Encoding utf8
    exit 1
}
