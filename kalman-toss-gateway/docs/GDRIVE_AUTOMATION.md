# Google Drive automation

Kalman can use the existing Colab state directly from Google Drive.

## Runtime contract

- rclone remote: `gdrive:`
- rclone config: `/etc/rclone/rclone.conf`
- mount: `/mnt/gdrive`
- `.env`: `KALMAN_DATA_ROOT=/mnt/gdrive`
- compatibility path: `/content/drive/MyDrive -> /mnt/gdrive`
- service: `kalman-gdrive.service`

`run_pipeline.sh` fails closed when the Drive mount is absent or unreadable. For KR it also reads the first four bytes of the historical seed and requires the Parquet `PAR1` magic before launching Python.

## One-time server setup

Configure OAuth first:

```bash
sudo rclone config --config /etc/rclone/rclone.conf
```

The remote must be named `gdrive`. Then:

```bash
sudo /opt/kalman/app/scripts/install_gdrive.sh
sudo /opt/kalman/app/scripts/preflight.sh
```

## Automation gate

Cron installation is intentionally blocked until all pipeline smoke tests succeed within the previous 24 hours:

```bash
sudo /opt/kalman/app/scripts/smoke_test.sh --pipelines
sudo /opt/kalman/app/scripts/install_cron.sh
```

The current schedule is stored in `config/kalman.cron.d`:

- CRYPTO_GLOBAL: hourly at minute 05
- KR_GLOBAL: 16:20 KST, Monday-Friday
- US: hourly across the KST windows covering US regular sessions in both DST and standard time
- auto-trade worker: 10 minutes after the US pipeline windows, but inert while trading gates remain closed

## Reboot verification

```bash
systemctl is-enabled kalman-gdrive.service
systemctl is-active kalman-gdrive.service
mountpoint /mnt/gdrive
readlink -f /content/drive/MyDrive
```

Live trading is not enabled by any Drive or cron installer.
