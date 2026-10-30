import type {
  RomInspectionLimits,
  RomInspectionResult,
  RomInspectionSample,
} from "@/__generated__";

async function base64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  }
  return btoa(binary);
}

export async function inspectionSample(
  file: File,
  limits: RomInspectionLimits,
): Promise<RomInspectionSample> {
  const [head, tail] = await Promise.all([
    base64(file.slice(0, limits.head_bytes)),
    base64(file.slice(Math.max(0, file.size - limits.tail_bytes))),
  ]);
  return { filename: file.name, size: file.size, head, tail };
}

export function inspectionConflict(
  result: RomInspectionResult,
  platformSlug: string,
): boolean {
  return (
    result.invalid ||
    result.platforms.length > 1 ||
    (result.platforms.length === 1 &&
      !result.platforms.includes(platformSlug)) ||
    result.incompatible_platforms.includes(platformSlug)
  );
}
