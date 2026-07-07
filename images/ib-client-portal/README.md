# IB Client Portal Docker Image

This directory documents the Docker image used for running Interactive Brokers
Client Portal API Gateway in the cluster.

## Upstream Image

We use the community-maintained image from
[Voyz/ibeam](https://github.com/Voyz/ibeam):

```
voyz/ibeam:latest
```

This image bundles:

- **Client Portal API Gateway** — REST/WebSocket gateway
- **Selenium & ChromeDriver** — automated browser login handler
- **pyvirtualdisplay** — virtual display buffer for headless login

## Key Ports

| Port | Description |
|------|-------------|
| 5000 | Gateway HTTPS port (default) |
| 5001 | Gateway HTTP port |

## Key Environment Variables

| Variable | Description |
|----------|-------------|
| `IBEAM_ACCOUNT` | IBKR account username |
| `IBEAM_PASSWORD` | IBKR account password |
| `IBEAM_GATEWAY_PORT` | The port the gateway will listen on (default 5000) |
| `IBEAM_RESTART_FAILED_AUTH` | Restarts gateway upon failed auth (default true) |
| `IBEAM_MAX_FAILED_AUTH` | Number of failed authentication attempts before exit |

## References

- [IBKR Client Portal Web API Documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/#introduction)
- [Voyz/ibeam on GitHub](https://github.com/Voyz/ibeam)
