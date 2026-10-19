import { FileText, Download, Mic } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/lib/chatMessage";
import { safeMediaUrl } from "@/lib/safeUrl";

interface MessageBodyProps {
    message: ChatMessage;
    isIncoming: boolean;
}

function fileNameFromUrl(url: string): string {
    try {
        const last = new URL(url, window.location.origin).pathname.split("/").pop();
        return decodeURIComponent(last || "arquivo");
    } catch {
        return "arquivo";
    }
}

export function MessageBody({ message, isIncoming }: MessageBodyProps) {
    const { message_type: type, content, buttons } = message;
    // Só http(s) ou /api/ (PDF da proposta): a URL pode ter vindo do texto do cliente.
    const url = safeMediaUrl(message.media_url);
    const isPdf = !!url && /\.pdf($|\?)/i.test(url);

    return (
        <div className="space-y-2">
            {type === "image" && url && (
                <a href={url} target="_blank" rel="noreferrer" className="block">
                    <img
                        src={url}
                        alt={content || "Imagem recebida"}
                        loading="lazy"
                        className="rounded-lg max-h-72 w-auto object-contain bg-black/5"
                    />
                </a>
            )}

            {type === "audio" && url && (
                <div className="space-y-1">
                    <audio controls preload="none" src={url} className="max-w-full h-10" />
                    {content && (
                        <p className="text-xs opacity-80 flex items-start gap-1">
                            <Mic className="w-3 h-3 mt-0.5 shrink-0" />
                            <span className="italic whitespace-pre-wrap break-words">{content}</span>
                        </p>
                    )}
                </div>
            )}

            {type === "file" && url && (
                <div className="space-y-2">
                    {isPdf && (
                        <iframe
                            src={url}
                            title={fileNameFromUrl(url)}
                            className="w-64 max-w-full h-72 rounded-lg bg-white hidden sm:block"
                        />
                    )}
                    <a
                        href={url}
                        target="_blank"
                        rel="noreferrer"
                        className={cn(
                            "flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium border",
                            isIncoming ? "bg-background/60 border-border/50" : "bg-white/10 border-white/20"
                        )}
                    >
                        <FileText className="w-4 h-4 shrink-0" />
                        <span className="truncate">{fileNameFromUrl(url)}</span>
                        <Download className="w-3.5 h-3.5 ml-auto shrink-0" />
                    </a>
                </div>
            )}

            {type !== "audio" && content && (
                <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">{content}</p>
            )}

            {buttons && buttons.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                    {buttons.map((b) => (
                        <span
                            key={b.id}
                            className={cn(
                                "text-[11px] px-2 py-0.5 rounded-full border",
                                isIncoming ? "border-border/60" : "border-white/40"
                            )}
                        >
                            {b.label}
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}
