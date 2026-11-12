param(
    [ValidateRange(0, 65535)]
    [int] $PreferredPort = 5000
)

$ErrorActionPreference = "Stop"
$listener = [System.Net.Sockets.TcpListener]::new(
    [System.Net.IPAddress]::Loopback, $PreferredPort
)
try {
    try {
        $listener.Start()
    } catch {
        $listener.Stop()
        $listener = [System.Net.Sockets.TcpListener]::new(
            [System.Net.IPAddress]::Loopback, 0
        )
        $listener.Start()
    }
    $listener.LocalEndpoint.Port
} finally {
    $listener.Stop()
}
