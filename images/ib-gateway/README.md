# IB Gateway Docker Image

This directory documents the Docker image used for running Interactive Brokers
Gateway in the cluster.

## Upstream Image

We use the community-maintained image from
[gnzsnz/ib-gateway-docker](https://github.com/gnzsnz/ib-gateway-docker):

```
ghcr.io/gnzsnz/ib-gateway:stable
```

This image bundles:

- **IB Gateway** – headless IBKR API gateway
- **IBC** (IB Controller) – automates login, daily restarts, and lifecycle
- **Xvfb** – virtual X11 framebuffer (required since IB Gateway is a Java GUI)
- **x11vnc** – optional VNC server for debugging the virtual display
- **socat** – proxy to expose the API port beyond localhost

## Key Ports

| Port | Description |
|------|-------------|
| 4001 | TWS API (live trading) |
| 4002 | TWS API (paper trading) |
| 5900 | VNC (virtual display, for debugging) |

## Key Environment Variables

| Variable | Description |
|----------|-------------|
| `TWS_USERID` | IBKR account username |
| `TWS_PASSWORD` | IBKR account password |
| `TRADING_MODE` | `paper` or `live` |
| `TWS_TOTP_KEY` | TOTP secret key for 2FA |
| `TWOFA_TIMEOUT_ACTION` | Action on 2FA timeout: `restart` or `exit` |
| `VNC_SERVER_PASSWORD` | Password for VNC access (optional) |
| `READ_ONLY_API` | Set to `no` to allow order placement |

## Persistence

Mount a volume to `/home/ibgateway/Jts` to persist session configuration
and settings across container restarts.

## References

- [IB Gateway Install & Setup (IBKR Campus)](https://www.interactivebrokers.com/campus/ibkr-quant-news/interactive-brokers-gateway-install-setup/)
- [gnzsnz/ib-gateway-docker on GitHub](https://github.com/gnzsnz/ib-gateway-docker)
- [IBC on GitHub](https://github.com/IbcAlpha/IBC)
