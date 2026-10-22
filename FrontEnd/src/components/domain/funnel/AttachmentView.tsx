import { FileText } from "lucide-react";
import { safeMediaUrl } from "@/lib/safeUrl";
import type { Attachment } from "@/hooks/useFunnel";

const IMAGE_RE = /[./](png|jpe?g|gif|webp)($|\?)/i;
const isImage = (a: Attachment) => IMAGE_RE.test(a.url) || IMAGE_RE.test(a.name || "");
const isPdf = (a: Attachment) => /\.pdf($|\?)/i.test(a.url) || /\.pdf$/i.test(a.name || "");

export function AttachmentView({ attachment }: { attachment: Attachment }) {
  const url = safeMediaUrl(attachment.url);
  if (!url) {
    return <p className="text-xs text-muted-foreground">{attachment.name} (endereço inválido)</p>;
  }
  if (isImage(attachment)) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="block">
        <img src={url} alt={attachment.name} className="rounded-lg max-h-48 w-full object-cover bg-muted" loading="lazy" />
        <span className="text-[11px] text-muted-foreground">{attachment.name}</span>
      </a>
    );
  }
  return (
    <div className="space-y-1">
      {isPdf(attachment) && (
        <iframe src={url} title={attachment.name} className="w-full h-56 rounded-lg bg-white hidden sm:block" />
      )}
      <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-2 text-xs underline">
        <FileText className="w-4 h-4" /> {attachment.name}
      </a>
    </div>
  );
}
