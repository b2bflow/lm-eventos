import type { ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export function NumberField({ label, value, onChange, step = 1, suffix }: {
  label: string; value: number; onChange: (v: number) => void; step?: number; suffix?: string;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}{suffix ? ` (${suffix})` : ""}</Label>
      <Input type="number" min={0} step={step} value={value || ""} placeholder="0"
        onChange={(e) => onChange(Number(e.target.value) || 0)} className="h-9" />
    </div>
  );
}

export function SwitchField({ id, label, checked, onChange }: {
  id: string; label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2 pt-5">
      <Switch checked={checked} onCheckedChange={onChange} id={id} />
      <Label htmlFor={id} className="text-sm">{label}</Label>
    </div>
  );
}

/** Seção de serviço opcional: a chave liga a seção; desligada, fica recolhida e não soma nada. */
export function ToggleSection({ id, title, hint, enabled, onToggle, children }: {
  id: string; title: string; hint?: string; enabled: boolean; onToggle: (v: boolean) => void; children: ReactNode;
}) {
  return (
    <section className="border-t border-border/50 pt-4">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="cursor-pointer">
          <span className="block text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</span>
          {hint && <span className="block text-xs font-normal text-muted-foreground mt-0.5">{hint}</span>}
        </Label>
        <Switch id={id} checked={enabled} onCheckedChange={onToggle} aria-label={title} />
      </div>
      {enabled && <div className="mt-3">{children}</div>}
    </section>
  );
}

export function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="border-t border-border/50 pt-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}
