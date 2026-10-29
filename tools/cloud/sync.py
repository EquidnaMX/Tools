"""
Cloud storage synchronization module.
Handles synchronization of DigitalOcean Spaces (S3-compatible) to local storage.
"""

import concurrent.futures
import fnmatch
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from tqdm import tqdm


class SyncStats:
    """Rastreo de estadísticas de sincronización."""

    def __init__(self):
        self.timestamp_start = datetime.now(timezone.utc).isoformat()
        self.timestamp_end = None
        self.downloaded: List[Dict] = []
        self.updated: List[Dict] = []
        self.skipped: List[Dict] = []
        self.deleted: List[Dict] = []
        self.errors: List[Dict] = []

    def add_downloaded(self, key: str, size_bytes: int, duration_sec: float):
        """Registra un archivo descargado."""
        self.downloaded.append(
            {
                "key": key,
                "size_bytes": size_bytes,
                "duration_sec": round(duration_sec, 2),
                "speed_mb_s": (
                    round((size_bytes / (1024 * 1024)) / duration_sec, 2)
                    if duration_sec > 0
                    else 0
                ),
            }
        )

    def add_updated(self, key: str, size_bytes: int):
        """Registra un archivo actualizado."""
        self.updated.append({"key": key, "size_bytes": size_bytes})

    def add_skipped(self, key: str, size_bytes: int):
        """Registra un archivo omitido."""
        self.skipped.append({"key": key, "size_bytes": size_bytes})

    def add_deleted(self, path: str):
        """Registra un archivo eliminado."""
        self.deleted.append({"path": str(path)})

    def add_error(self, key: str, error: str):
        """Registra un error."""
        self.errors.append({"key": key, "error": error})

    def finalize(self):
        """Marca el fin de la sincronización."""
        self.timestamp_end = datetime.now(timezone.utc).isoformat()

    def get_duration_seconds(self) -> float:
        """Retorna duración total en segundos."""
        if self.timestamp_end is None:
            return 0
        start = datetime.fromisoformat(self.timestamp_start)
        end = datetime.fromisoformat(self.timestamp_end)
        return (end - start).total_seconds()

    def to_dict(self, include_details: bool = False) -> Dict:
        """Convierte a diccionario para JSON."""
        total_bytes_downloaded = sum(f["size_bytes"] for f in self.downloaded)
        total_bytes_updated = sum(f["size_bytes"] for f in self.updated)
        total_bytes_skipped = sum(f["size_bytes"] for f in self.skipped)

        duration = self.get_duration_seconds()

        report = {
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": round(duration, 2),
            "status": "success" if not self.errors else "completed_with_errors",
            "counts": {
                "downloaded": len(self.downloaded),
                "updated": len(self.updated),
                "skipped": len(self.skipped),
                "deleted": len(self.deleted),
                "errors": len(self.errors),
                "total": len(self.downloaded) + len(self.updated) + len(self.skipped),
            },
            "bytes": {
                "downloaded": total_bytes_downloaded,
                "updated": total_bytes_updated,
                "skipped": total_bytes_skipped,
                "total": total_bytes_downloaded
                + total_bytes_updated
                + total_bytes_skipped,
            },
            "throughput_mb_s": (
                round((total_bytes_downloaded / (1024 * 1024)) / duration, 2)
                if duration > 0
                else 0
            ),
            "throughput_gb": round((total_bytes_downloaded / (1024**3)), 2),
        }

        # Incluir detalles si se solicita
        if include_details:
            report["details"] = {
                "downloaded": self.downloaded if self.downloaded else [],
                "updated": self.updated if self.updated else [],
                "deleted": self.deleted if self.deleted else [],
                "errors": self.errors if self.errors else [],
            }

        return report


class UploadStats:
    """Rastreo de estadísticas de upload."""

    def __init__(self):
        self.timestamp_start = datetime.now(timezone.utc).isoformat()
        self.timestamp_end = None
        self.uploaded: List[Dict] = []
        self.updated: List[Dict] = []
        self.skipped: List[Dict] = []
        self.deleted: List[Dict] = []
        self.errors: List[Dict] = []

    def add_uploaded(self, key: str, size_bytes: int, duration_sec: float):
        """Registra un archivo subido."""
        self.uploaded.append(
            {
                "key": key,
                "size_bytes": size_bytes,
                "duration_sec": round(duration_sec, 2),
                "speed_mb_s": (
                    round((size_bytes / (1024 * 1024)) / duration_sec, 2)
                    if duration_sec > 0
                    else 0
                ),
            }
        )

    def add_updated(self, key: str, size_bytes: int):
        """Registra un archivo actualizado."""
        self.updated.append({"key": key, "size_bytes": size_bytes})

    def add_skipped(self, key: str, size_bytes: int):
        """Registra un archivo omitido."""
        self.skipped.append({"key": key, "size_bytes": size_bytes})

    def add_deleted(self, key: str):
        """Registra un archivo eliminado del bucket."""
        self.deleted.append({"key": key})

    def add_error(self, path: str, error: str):
        """Registra un error."""
        self.errors.append({"path": path, "error": error})

    def finalize(self):
        """Marca el fin del upload."""
        self.timestamp_end = datetime.now(timezone.utc).isoformat()

    def get_duration_seconds(self) -> float:
        """Retorna duración total en segundos."""
        if self.timestamp_end is None:
            return 0
        start = datetime.fromisoformat(self.timestamp_start)
        end = datetime.fromisoformat(self.timestamp_end)
        return (end - start).total_seconds()

    def to_dict(self, include_details: bool = False) -> Dict:
        """Convierte a diccionario para JSON."""
        total_bytes_uploaded = sum(f["size_bytes"] for f in self.uploaded)
        total_bytes_updated = sum(f["size_bytes"] for f in self.updated)
        total_bytes_skipped = sum(f["size_bytes"] for f in self.skipped)

        duration = self.get_duration_seconds()

        report = {
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": round(duration, 2),
            "status": "success" if not self.errors else "completed_with_errors",
            "counts": {
                "uploaded": len(self.uploaded),
                "updated": len(self.updated),
                "skipped": len(self.skipped),
                "deleted": len(self.deleted),
                "errors": len(self.errors),
                "total": len(self.uploaded) + len(self.updated) + len(self.skipped),
            },
            "bytes": {
                "uploaded": total_bytes_uploaded,
                "updated": total_bytes_updated,
                "skipped": total_bytes_skipped,
                "total": total_bytes_uploaded
                + total_bytes_updated
                + total_bytes_skipped,
            },
            "throughput_mb_s": (
                round((total_bytes_uploaded / (1024 * 1024)) / duration, 2)
                if duration > 0
                else 0
            ),
            "throughput_gb": round((total_bytes_uploaded / (1024**3)), 2),
        }

        # Incluir detalles si se solicita
        if include_details:
            report["details"] = {
                "uploaded": self.uploaded if self.uploaded else [],
                "updated": self.updated if self.updated else [],
                "deleted": self.deleted if self.deleted else [],
                "errors": self.errors if self.errors else [],
            }

        return report


def save_json_report(report_data: Dict, filename: str, logger: logging.Logger):
    """Guarda el reporte en archivo JSON."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        logger.info(f"📊 Reporte JSON guardado en: {filename}")
    except Exception as e:
        logger.error(f"✗ Error al guardar reporte JSON: {e}")


class DigitalOceanSync:
    """Clase para sincronizar DigitalOcean Spaces a local."""

    def __init__(
        self,
        region: str,
        bucket: str,
        dest: str,
        prefix: str = "",
        profile: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        workers: int = 16,
        delete: bool = False,
        dry_run: bool = False,
        exclude: List[str] = None,
        show_progress: bool = True,
        logger: logging.Logger = None,
    ):
        """
        Inicializa el sincronizador.

        Args:
            region: Región de DigitalOcean (sfo3, nyc3, etc.)
            bucket: Nombre del bucket
            dest: Carpeta local destino
            prefix: Prefijo opcional en el bucket
            profile: Perfil AWS a usar
            access_key: AWS Access Key ID
            secret_key: AWS Secret Access Key
            workers: Número de workers paralelos
            delete: Modo espejo (elimina locales huérfanos)
            dry_run: Modo simulación
            exclude: Patrones a excluir
            show_progress: Mostrar barras de progreso
            logger: Logger a usar
        """
        self.region = region
        self.bucket = bucket
        self.dest_root = Path(dest).resolve()
        self.prefix = prefix
        self.profile = profile
        self.access_key = access_key
        self.secret_key = secret_key
        self.workers = workers
        self.delete = delete
        self.dry_run = dry_run
        self.exclude = exclude or []
        self.show_progress = show_progress
        self.logger = logger or logging.getLogger(__name__)
        self.stats = SyncStats()

        # Cliente S3 (se crea al llamar sync())
        self.client = None

    def _build_client(self) -> object:
        """Crea un cliente S3 apuntando al endpoint de DigitalOcean Spaces."""
        try:
            session_kwargs = {}
            if self.profile:
                session_kwargs["profile_name"] = self.profile
                self.logger.info(f"📌 Usando perfil AWS: {self.profile}")

            session = (
                boto3.Session(**session_kwargs) if session_kwargs else boto3.Session()
            )

            endpoint = f"https://{self.region}.digitaloceanspaces.com"
            self.logger.debug(f"🔗 Endpoint: {endpoint}")

            client = session.client(
                "s3",
                region_name=self.region,
                endpoint_url=endpoint,
                aws_access_key_id=self.access_key or os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=self.secret_key
                or os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(
                    retries={"max_attempts": 10, "mode": "standard"},
                    signature_version="s3v4",
                    read_timeout=120,
                    connect_timeout=30,
                ),
            )

            # Evita el intento de usar metadatos EC2
            os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
            self.logger.info(f"✓ Cliente S3 creado para región: {self.region}")
            return client

        except Exception as e:
            self.logger.error(f"✗ Error al crear cliente S3: {e}")
            raise

    def _validate_credentials(self) -> bool:
        """Valida que las credenciales sean válidas antes de empezar."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            self.logger.info(
                f"✓ Credenciales válidas | Bucket accesible: {self.bucket}"
            )
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "404":
                self.logger.error(f"✗ Bucket no existe: {self.bucket}")
            elif error_code == "403":
                self.logger.error(f"✗ Acceso denegado al bucket: {self.bucket}")
            else:
                self.logger.error(f"✗ Error al validar credenciales: {e}")
            return False
        except Exception as e:
            self.logger.error(f"✗ Error inesperado al validar credenciales: {e}")
            return False

    def _list_objects(self) -> Iterable[dict]:
        """Lista objetos del bucket con paginación."""
        paginator = self.client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)

        for page in page_iterator:
            if "Contents" in page:
                for obj in page["Contents"]:
                    yield obj

    def _download_file(self, obj: dict) -> Tuple[str, bool, Optional[str], float]:
        """
        Descarga un objeto.
        Retorna (key, descargado(bool), error(str|None), duration_sec).
        """
        key = obj["Key"]
        last_modified = obj["LastModified"]
        local_path = self.dest_root.joinpath(*key.split("/"))
        self._ensure_parent(local_path)

        start_time = time.time()

        if self.dry_run:
            self.logger.debug(f"[DRY-RUN] Descargaría: {key}")
            return key, False, None, 0.0

        attempts = 0
        while attempts < 5:
            attempts += 1
            try:
                resp = self.client.get_object(Bucket=self.bucket, Key=key)
                body = resp["Body"]
                total = int(resp["ContentLength"])

                tmp_path = local_path.with_suffix(local_path.suffix + ".part")
                chunk = 1024 * 1024

                if self.show_progress:
                    with tqdm(
                        total=total, unit="B", unit_scale=True, desc=key, leave=False
                    ) as pbar:
                        with open(tmp_path, "wb") as f:
                            while True:
                                data = body.read(chunk)
                                if not data:
                                    break
                                f.write(data)
                                pbar.update(len(data))
                else:
                    with open(tmp_path, "wb") as f:
                        while True:
                            data = body.read(chunk)
                            if not data:
                                break
                            f.write(data)

                os.replace(tmp_path, local_path)

                # Ajusta mtime local al del objeto remoto
                ts = (
                    last_modified.replace(tzinfo=timezone.utc).timestamp()
                    if last_modified.tzinfo
                    else last_modified.timestamp()
                )
                os.utime(local_path, (ts, ts))

                duration = time.time() - start_time
                self.logger.debug(
                    f"✓ Descargado: {key} ({total:,} bytes en {duration:.2f}s)"
                )

                self.stats.add_downloaded(key, total, duration)

                return key, True, None, duration

            except (ClientError, BotoCoreError, OSError) as e:
                err = f"{type(e).__name__}: {e}"
                if attempts < 5:
                    wait = 1.5 * attempts
                    self.logger.warning(
                        f"⚠ Error en {key} (intento {attempts}/5): {err}. Reintentando en {wait}s..."
                    )
                    time.sleep(wait)
                else:
                    self.logger.error(
                        f"✗ Falló {key} después de {attempts} intentos: {err}"
                    )
                    self.stats.add_error(key, err)

        duration = time.time() - start_time
        return key, False, f"Error tras {attempts} reintentos", duration

    def _should_exclude(self, key: str) -> bool:
        """Verifica si una clave debe ser excluida según los patrones."""
        if not self.exclude:
            return False
        win_key = key.replace("/", os.sep)
        for pat in self.exclude:
            if fnmatch.fnmatch(key, pat) or fnmatch.fnmatch(win_key, pat):
                return True
        return False

    def _local_up_to_date(
        self, local_path: Path, s3_size: int, s3_last_modified
    ) -> bool:
        """
        Considera actualizado si coinciden tamaño y mtime (±2s).
        Evitamos depender de ETag (no es fiable con subidas multiparte).
        """
        if not local_path.is_file():
            return False
        try:
            stat = local_path.stat()
            if stat.st_size != s3_size:
                return False
            local_mtime = stat.st_mtime
            ts_remote = (
                s3_last_modified.replace(tzinfo=timezone.utc).timestamp()
                if s3_last_modified.tzinfo
                else s3_last_modified.timestamp()
            )
            return abs(local_mtime - ts_remote) < 2.0
        except OSError:
            return False

    def _ensure_parent(self, path: Path):
        """Crea directorios padres si no existen."""
        path.parent.mkdir(parents=True, exist_ok=True)

    def sync(self) -> SyncStats:
        """
        Ejecuta la sincronización completa.

        Returns:
            SyncStats con estadísticas de la operación
        """
        try:
            # Crear destino
            self.dest_root.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"✓ Directorio destino preparado: {self.dest_root}")

            # Crear cliente S3
            self.client = self._build_client()

            # Validar credenciales
            if not self._validate_credentials():
                self.logger.critical(
                    "✗ No se pudo validar las credenciales. Abortando."
                )
                raise RuntimeError("Credenciales inválidas o bucket inaccesible")

            # Listar objetos remotos
            self.logger.info(
                f"📦 Listando objetos en s3://{self.bucket}/{self.prefix or ''} ..."
            )
            objs = []
            total_bytes = 0
            for obj in self._list_objects():
                if self._should_exclude(obj["Key"]):
                    self.logger.debug(f"⏭️  Excluido por patrón: {obj['Key']}")
                    continue
                objs.append(obj)
                total_bytes += obj["Size"]

            self.logger.info(
                f"📦 Objetos encontrados: {len(objs):,} | Tamaño total: {total_bytes / (1024**3):.2f} GB"
            )

            # Decidir qué descargar
            self.logger.info("🔍 Verificando qué necesita descargarse...")
            to_download = []
            skipped = 0
            for obj in objs:
                key = obj["Key"]
                local_path = self.dest_root.joinpath(*key.split("/"))
                if self._local_up_to_date(local_path, obj["Size"], obj["LastModified"]):
                    skipped += 1
                    self.logger.debug(f"⏭️  Ya actualizado: {key}")
                    self.stats.add_skipped(key, obj["Size"])
                    continue
                to_download.append(obj)

            self.logger.info(
                f"📥 Archivos a descargar/actualizar: {len(to_download):,}"
            )
            self.logger.info(f"⏭️  Archivos ya actualizados (omitidos): {skipped:,}")

            errors: List[str] = []
            downloaded_count = 0

            # Descargar en paralelo
            if not self.dry_run and to_download:
                self.logger.info(
                    f"⬇️  Iniciando descarga paralela con {self.workers} workers..."
                )
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.workers
                ) as ex:
                    futures = [
                        ex.submit(self._download_file, obj) for obj in to_download
                    ]
                    for future in tqdm(
                        concurrent.futures.as_completed(futures),
                        total=len(futures),
                        unit="file",
                        desc="Descargando",
                    ):
                        key, ok, err, duration = future.result()
                        if ok:
                            downloaded_count += 1
                        if err:
                            errors.append(f"{key}: {err}")

            elif self.dry_run:
                self.logger.info(
                    "📋 [DRY-RUN] Simulando descarga de {} archivos...".format(
                        len(to_download)
                    )
                )
                for obj in to_download:
                    key, ok, err, duration = self._download_file(obj)

            # Modo espejo: eliminar locales huérfanos
            deleted = 0
            if self.delete:
                self.logger.info(
                    "🔍 Modo DELETE: buscando archivos locales huérfanos..."
                )
                remote_keys = set(o["Key"] for o in objs)
                orphans = 0
                for local_path in self.dest_root.rglob("*"):
                    if not local_path.is_file():
                        continue
                    rel = local_path.relative_to(self.dest_root).as_posix()
                    expected_key = (
                        rel if not self.prefix else f"{self.prefix.rstrip('/')}/{rel}"
                    )
                    if expected_key not in remote_keys and not self._should_exclude(
                        expected_key
                    ):
                        orphans += 1
                        self.logger.warning(f"🗑️  Huérfano encontrado: {local_path}")
                        if not self.dry_run:
                            try:
                                local_path.unlink(missing_ok=True)
                                deleted += 1
                                self.stats.add_deleted(str(local_path))
                                self.logger.info(f"✓ Eliminado: {local_path}")
                            except OSError as e:
                                errors.append(f"Delete {local_path}: {e}")
                                self.logger.error(
                                    f"✗ Error al eliminar {local_path}: {e}"
                                )
                self.logger.info(
                    f"🗑️  Huérfanos encontrados: {orphans} | Eliminados: {deleted}"
                )

            # Resumen final
            self.logger.info("=" * 60)
            self.logger.info("📊 RESUMEN FINAL")
            self.logger.info("=" * 60)
            self.logger.info(f"  Total remotos considerados:  {len(objs):,}")
            self.logger.info(
                f"  Descargados/actualizados:    {downloaded_count:,}{' (DRY-RUN)' if self.dry_run else ''}"
            )
            self.logger.info(f"  Ya actualizados (omitidos):  {skipped:,}")
            if self.delete:
                self.logger.info(
                    f"  Eliminados locales:          {deleted:,}{' (DRY-RUN)' if self.dry_run else ''}"
                )

            if errors:
                self.logger.error(f"  ⚠️  Errores encontrados:    {len(errors)}")
                for e in errors[:10]:
                    self.logger.error(f"      - {e}")
                if len(errors) > 10:
                    self.logger.error(f"      ... y {len(errors) - 10} más")

            # Finalizar estadísticas
            self.stats.finalize()

            self.logger.info("=" * 60)
            if errors:
                self.logger.warning("⚠️  SINCRONIZACIÓN COMPLETADA CON ERRORES")
            else:
                self.logger.info("✅ SINCRONIZACIÓN COMPLETADA EXITOSAMENTE")
            self.logger.info("=" * 60)

            return self.stats

        except Exception as e:
            self.logger.critical(f"✗ Error crítico: {e}", exc_info=True)
            raise

    def upload(self, source: str, dest_prefix: str = "", **kwargs) -> UploadStats:
        """
        Sube archivos locales al bucket de DigitalOcean Spaces.

        Args:
            source: Ruta local del archivo o directorio a subir
            dest_prefix: Prefijo de destino en el bucket (path dentro del bucket)
            **kwargs: Argumentos adicionales (acl, content_type, metadata, etc.)

        Returns:
            UploadStats con las estadísticas de la operación
        """
        source_path = Path(source).resolve()
        upload_stats = UploadStats()

        # Crear cliente si no existe
        if not self.client:
            self.client = self._build_client()
            if not self._validate_credentials():
                raise RuntimeError("Credenciales inválidas o bucket inaccesible")

        self.logger.info("=" * 60)
        self.logger.info("☁️  INICIANDO UPLOAD A DIGITALOCEAN SPACES")
        self.logger.info("=" * 60)
        self.logger.info(f"📂 Fuente local:            {source_path}")
        self.logger.info(f"🪣 Bucket destino:          {self.bucket}")
        self.logger.info(f"📍 Región:                  {self.region}")
        self.logger.info(f"📁 Prefijo destino:         {dest_prefix or '(raíz)'}")
        self.logger.info(f"👷 Workers:                 {self.workers}")
        if self.dry_run:
            self.logger.info("🧪 Modo:                    DRY-RUN (simulación)")
        if self.exclude:
            self.logger.info(f"🚫 Exclusiones:             {', '.join(self.exclude)}")
        self.logger.info("=" * 60)

        try:
            if not source_path.exists():
                raise FileNotFoundError(f"Ruta no encontrada: {source_path}")

            # Recolectar archivos a subir
            files_to_upload = []

            if source_path.is_file():
                files_to_upload.append(source_path)
                self.logger.info(f"📄 Subiendo archivo individual: {source_path.name}")
            else:
                self.logger.info(f"📁 Escaneando directorio: {source_path}")
                for file_path in source_path.rglob("*"):
                    if file_path.is_file():
                        # Aplicar exclusiones
                        relative_path = str(file_path.relative_to(source_path))
                        if self._should_exclude(relative_path):
                            self.logger.debug(f"⏭️  Excluido: {relative_path}")
                            continue
                        files_to_upload.append(file_path)

                self.logger.info(
                    f"📊 Total archivos a procesar: {len(files_to_upload):,}"
                )

            # Listar objetos existentes en el bucket para comparar
            self.logger.info("🔍 Listando objetos existentes en bucket...")
            existing_objects = {}
            for obj in self._list_objects():
                key = obj["Key"]
                if dest_prefix and not key.startswith(dest_prefix):
                    continue
                existing_objects[key] = obj

            self.logger.info(
                f"📦 Objetos en bucket (prefijo '{dest_prefix}'): {len(existing_objects):,}"
            )

            # Procesar archivos con ThreadPoolExecutor
            total_bytes = sum(f.stat().st_size for f in files_to_upload)
            self.logger.info(
                f"💾 Tamaño total a subir: {total_bytes / (1024**3):.2f} GB"
            )

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.workers
            ) as executor:
                # Crear progress bar si está habilitado
                if self.show_progress and files_to_upload:
                    pbar = tqdm(
                        total=total_bytes,
                        unit="B",
                        unit_scale=True,
                        desc="⬆️  Subiendo",
                        disable=not self.show_progress,
                    )
                else:
                    pbar = None

                # Función para subir un archivo
                def upload_one(file_path: Path):
                    try:
                        # Calcular key en el bucket
                        if source_path.is_file():
                            key = (
                                dest_prefix + file_path.name
                                if dest_prefix
                                else file_path.name
                            )
                        else:
                            relative = file_path.relative_to(source_path)
                            key = (
                                f"{dest_prefix}/{relative}".replace("\\", "/")
                                if dest_prefix
                                else str(relative).replace("\\", "/")
                            )

                        # Verificar si necesita subir
                        file_size = file_path.stat().st_size
                        file_mtime = file_path.stat().st_mtime

                        if key in existing_objects:
                            remote_size = existing_objects[key].get("Size", 0)
                            remote_mtime = existing_objects[key].get("LastModified")

                            # Comparar tamaño y fecha
                            if remote_size == file_size:
                                if remote_mtime:
                                    # Convertir a timestamp para comparar
                                    remote_ts = (
                                        remote_mtime.timestamp()
                                        if hasattr(remote_mtime, "timestamp")
                                        else 0
                                    )
                                    if (
                                        file_mtime <= remote_ts + 1
                                    ):  # +1 seg de tolerancia
                                        upload_stats.add_skipped(key, file_size)
                                        if pbar:
                                            pbar.update(file_size)
                                        return

                        # Subir archivo
                        start_time = time.time()

                        if not self.dry_run:
                            # Determinar content-type
                            content_type = kwargs.get("content_type")
                            if not content_type:
                                import mimetypes

                                content_type, _ = mimetypes.guess_type(str(file_path))
                                content_type = (
                                    content_type or "application/octet-stream"
                                )

                            # Preparar extra_args
                            extra_args = {"ContentType": content_type}

                            # ACL si se especifica
                            if "acl" in kwargs:
                                extra_args["ACL"] = kwargs["acl"]

                            # Metadata si se especifica
                            if "metadata" in kwargs:
                                extra_args["Metadata"] = kwargs["metadata"]

                            # Subir con retry
                            max_retries = 3
                            for attempt in range(max_retries):
                                try:
                                    self.client.upload_file(
                                        str(file_path),
                                        self.bucket,
                                        key,
                                        ExtraArgs=extra_args,
                                    )
                                    break
                                except Exception as e:
                                    if attempt == max_retries - 1:
                                        raise
                                    self.logger.debug(
                                        f"⚠️  Reintento {attempt + 1}/{max_retries} para {key}: {e}"
                                    )
                                    time.sleep(2**attempt)

                        duration = time.time() - start_time

                        if key in existing_objects:
                            upload_stats.add_updated(key, file_size)
                        else:
                            upload_stats.add_uploaded(key, file_size, duration)

                        if pbar:
                            pbar.update(file_size)

                    except Exception as e:
                        error_msg = str(e)
                        upload_stats.add_error(str(file_path), error_msg)
                        self.logger.error(f"✗ Error subiendo {file_path}: {error_msg}")
                        if pbar:
                            pbar.update(
                                file_path.stat().st_size if file_path.exists() else 0
                            )

                # Ejecutar uploads en paralelo
                list(executor.map(upload_one, files_to_upload))

                if pbar:
                    pbar.close()

            # Resumen final
            uploaded = len(upload_stats.uploaded)
            updated = len(upload_stats.updated)
            skipped = len(upload_stats.skipped)
            errors = upload_stats.errors

            self.logger.info("=" * 60)
            self.logger.info("📊 RESUMEN DE UPLOAD")
            self.logger.info("=" * 60)
            self.logger.info(
                f"  Archivos nuevos subidos:    {uploaded:,}{' (DRY-RUN)' if self.dry_run else ''}"
            )
            self.logger.info(
                f"  Archivos actualizados:      {updated:,}{' (DRY-RUN)' if self.dry_run else ''}"
            )
            self.logger.info(f"  Archivos omitidos:          {skipped:,}")

            if errors:
                self.logger.error(f"  ⚠️  Errores encontrados:    {len(errors)}")
                for e in errors[:10]:
                    self.logger.error(f"      - {e['path']}: {e['error']}")
                if len(errors) > 10:
                    self.logger.error(f"      ... y {len(errors) - 10} más")

            # Finalizar estadísticas
            upload_stats.finalize()

            self.logger.info("=" * 60)
            if errors:
                self.logger.warning("⚠️  UPLOAD COMPLETADO CON ERRORES")
            else:
                self.logger.info("✅ UPLOAD COMPLETADO EXITOSAMENTE")
            self.logger.info("=" * 60)

            return upload_stats

        except Exception as e:
            self.logger.critical(f"✗ Error crítico en upload: {e}", exc_info=True)
            raise
