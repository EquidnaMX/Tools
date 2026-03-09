#!/usr/bin/env python3
"""
Ejemplos de uso del módulo System.

Demuestra las capacidades de timezone_manager y file_manager.
"""

from pathlib import Path
from tools.system import TimezoneManager, FileManager


def example_timezone_operations():
    """Ejemplos de operaciones con timezone."""
    print("=" * 60)
    print("EJEMPLOS: TimezoneManager")
    print("=" * 60)
    
    manager = TimezoneManager()
    
    # 1. Obtener timezone actual
    print("\n1. Obtener timezone actual:")
    current_tz = manager.get_current_timezone()
    print(f"   Timezone actual: {current_tz}")
    
    # 2. Información detallada
    print("\n2. Información detallada:")
    info = manager.get_timezone_info()
    print(f"   Platform: {info['platform']}")
    print(f"   Timezone: {info['timezone']}")
    
    # 3. Listar timezones disponibles (primeros 10)
    print("\n3. Timezones disponibles (primeros 10):")
    zones = manager.list_available_timezones()[:10]
    for zone in zones:
        print(f"   - {zone}")
    
    # 4. Filtrar por región
    print("\n4. Timezones de América (primeros 5):")
    all_zones = manager.list_available_timezones()
    america_zones = [z for z in all_zones if z.startswith("America/")][:5]
    for zone in america_zones:
        print(f"   - {zone}")


def example_file_operations():
    """Ejemplos de operaciones con archivos."""
    print("\n" + "=" * 60)
    print("EJEMPLOS: FileManager")
    print("=" * 60)
    
    manager = FileManager()
    
    # Crear directorio temporal para ejemplos
    temp_dir = Path("./temp_example")
    temp_dir.mkdir(exist_ok=True)
    
    try:
        # 1. Crear archivos de ejemplo
        print("\n1. Creando archivos de ejemplo...")
        (temp_dir / "file1.txt").write_text("Contenido del archivo 1\n")
        (temp_dir / "file2.txt").write_text("Contenido del archivo 2\n")
        (temp_dir / "empty.txt").write_text("")
        (temp_dir / "whitespace.txt").write_text("   \n\n   \n")
        (temp_dir / "data.log").write_text("Log entry 1\nLog entry 2\n")
        print("   ✓ Archivos creados en temp_example/")
        
        # 2. Buscar archivos por patrón
        print("\n2. Buscar archivos .txt:")
        txt_files = manager.find_files_by_pattern(temp_dir, "*.txt")
        for file in txt_files:
            print(f"   - {file.name}")
        
        # 3. Estadísticas del directorio
        print("\n3. Estadísticas del directorio:")
        stats = manager.get_directory_stats(temp_dir)
        print(f"   Total archivos: {stats['total_files']}")
        print(f"   Tamaño total: {stats['total_size']} bytes")
        print(f"   Archivos vacíos: {stats['empty_files']}")
        
        # 4. Eliminar archivos vacíos (dry-run)
        print("\n4. Eliminar archivos vacíos (DRY RUN):")
        clean_stats = manager.delete_empty_files(temp_dir, dry_run=True)
        print(f"   Archivos procesados: {clean_stats.processed}")
        print(f"   Se eliminarían: {clean_stats.deleted}")
        
        # 5. Fusionar archivos .txt
        print("\n5. Fusionar archivos .txt:")
        output_file = temp_dir / "merged.txt"
        merge_stats = manager.merge_files(
            source_dir=temp_dir,
            output_file=output_file,
            pattern="*.txt",
            separator="---",
            exclude_empty_lines=True,
            overwrite=True
        )
        print(f"   Archivos fusionados: {merge_stats.merged}")
        print(f"   Tamaño total: {merge_stats.total_size} bytes")
        
        # Mostrar contenido fusionado
        if output_file.exists():
            print(f"\n   Contenido de {output_file.name}:")
            content = output_file.read_text()
            for line in content.split('\n')[:10]:  # Primeras 10 líneas
                print(f"     {line}")
        
    finally:
        # Limpiar directorio temporal
        print("\n6. Limpiando archivos de ejemplo...")
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("   ✓ Directorio temporal eliminado")


def example_cli_usage():
    """Mostrar ejemplos de uso del CLI."""
    print("\n" + "=" * 60)
    print("EJEMPLOS: Uso del CLI")
    print("=" * 60)
    
    print("\n# Timezone management:")
    print("python -m tools.cli.main system timezone get")
    print("python -m tools.cli.main system timezone set UTC")
    print("python -m tools.cli.main system timezone list --filter America")
    
    print("\n# File operations:")
    print("python -m tools.cli.main system files clean-empty /path/to/dir --dry-run")
    print("python -m tools.cli.main system files merge /source output.txt --pattern '*.log'")
    print("python -m tools.cli.main system files stats /path/to/dir --json")
    print("python -m tools.cli.main system files find /path '*.txt' --recursive")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("EJEMPLOS DE USO: Módulo System")
    print("=" * 60)
    
    # Ejecutar ejemplos
    example_timezone_operations()
    example_file_operations()
    example_cli_usage()
    
    print("\n" + "=" * 60)
    print("Para más información, ver: tools/system/README.md")
    print("=" * 60 + "\n")
