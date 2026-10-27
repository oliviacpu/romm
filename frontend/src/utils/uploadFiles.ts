const droppedPaths = new WeakMap<File, string>();

export function uploadPath(file: File): string {
  return droppedPaths.get(file) || file.webkitRelativePath || file.name;
}

export async function droppedFiles(
  items: DataTransferItemList,
): Promise<File[]> {
  const files: File[] = [];

  async function visit(entry: FileSystemEntry, parent: string): Promise<void> {
    const path = parent ? `${parent}/${entry.name}` : entry.name;
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) => {
        (entry as FileSystemFileEntry).file(resolve, reject);
      });
      droppedPaths.set(file, path);
      files.push(file);
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      while (true) {
        const entries = await new Promise<FileSystemEntry[]>(
          (resolve, reject) => {
            reader.readEntries(resolve, reject);
          },
        );
        if (entries.length === 0) break;
        for (const child of entries) await visit(child, path);
      }
    }
  }

  for (const item of Array.from(items)) {
    const entry = item.webkitGetAsEntry?.();
    if (entry) {
      await visit(entry, "");
    } else {
      const file = item.getAsFile();
      if (file) files.push(file);
    }
  }
  return files;
}
