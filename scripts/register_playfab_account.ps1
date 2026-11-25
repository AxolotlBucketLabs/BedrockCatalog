$ErrorActionPreference = "Stop"

$titleId = "20ca2"
$baseUrl = "https://$titleId.playfabapi.com"

function Invoke-PlayFabRequest {
	param(
		[Parameter(Mandatory = $true)]
		[string] $Path,
		[Parameter(Mandatory = $true)]
		[hashtable] $Payload,
		[Parameter(Mandatory = $true)]
		[string] $Operation
	)

	try {
		return Invoke-RestMethod `
			-Uri "$baseUrl/$Path" `
			-Method Post `
			-ContentType "application/json" `
			-Body ($Payload | ConvertTo-Json -Depth 5 -Compress) `
			-TimeoutSec 30 `
			-ErrorAction Stop
	} catch {
		$statusCode = $null
		try {
			$statusCode = [int] $_.Exception.Response.StatusCode
		} catch {
			$statusCode = $null
		}

		if ($null -ne $statusCode -and $statusCode -gt 0) {
			throw "PlayFab rejected the $Operation request with HTTP $statusCode. The title may not allow this operation. No credentials were printed."
		}

		throw "Could not reach PlayFab for the $Operation request. Check the network connection and try again. No credentials were printed."
	}
}

$mode = (Read-Host "Choose [L]og in to an existing account or [R]egister a new one (L)").Trim().ToLowerInvariant()
if ([string]::IsNullOrWhiteSpace($mode)) {
	$mode = "l"
}
if ($mode -notin @("l", "r")) {
	throw "Choose L to log in or R to register."
}

$username = $null
if ($mode -eq "r") {
	$username = (Read-Host "Choose a PlayFab username, 3 to 20 characters").Trim()
}
$email = (Read-Host "Email for the account").Trim()
$securePassword = Read-Host "PlayFab password" -AsSecureString
$password = [System.Net.NetworkCredential]::new("", $securePassword).Password

try {
	if ($mode -eq "r") {
		$registration = Invoke-PlayFabRequest `
			-Path "Client/RegisterPlayFabUser" `
			-Operation "account registration" `
			-Payload @{
				TitleId = $titleId
				Username = $username
				Email = $email
				Password = $password
				RequireBothUsernameAndEmail = $true
			}

		$playFabId = $registration.data.PlayFabId
		if ([string]::IsNullOrWhiteSpace([string] $playFabId)) {
			throw "PlayFab did not confirm account registration. No credentials were printed."
		}
	}

	$login = Invoke-PlayFabRequest `
		-Path "Client/LoginWithEmailAddress" `
		-Operation "login verification" `
		-Payload @{
			TitleId = $titleId
			Email = $email
			Password = $password
		}

	if ([string]::IsNullOrWhiteSpace([string] $login.data.SessionTicket)) {
		throw "The account was created, but PlayFab did not return a login session. No credentials were printed."
	}

	$env:PLAYFAB_EMAIL = $email
	$env:PLAYFAB_PASSWORD = $password

	if ($mode -eq "r") {
		Write-Host "PlayFab account registration and login succeeded."
	} else {
		Write-Host "PlayFab login succeeded."
	}
	Write-Host "Credentials are available only in this PowerShell session. They were not saved to a file."
	Write-Host "Run the catalog update in this same window: python scripts/update_catalog.py"
	Write-Host "Close this PowerShell window when finished to clear the session credentials."
} finally {
	$password = $null
	$securePassword.Dispose()
}
