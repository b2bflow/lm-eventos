import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export interface ResponsiveColumn<T> {
  id: string;
  header: string;
  cell: (row: T) => ReactNode;
  // Coluna principal: vira o título do cartão no celular.
  primary?: boolean;
  // Não aparece no cartão do celular (fica só na tabela).
  hideOnMobile?: boolean;
  align?: "left" | "right";
  className?: string;
}

interface ResponsiveTableProps<T> {
  columns: ResponsiveColumn<T>[];
  rows: T[];
  getId: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyText?: string;
  loading?: boolean;
}

// Lista de registros: tabela a partir de md e cartões empilhados no celular (nada de rolagem lateral nem coluna espremida).
export function ResponsiveTable<T>({ columns, rows, getId, onRowClick, emptyText = "Nada encontrado.", loading }: ResponsiveTableProps<T>) {
  const primary = columns.find((column) => column.primary) ?? columns[0];
  const details = columns.filter((column) => column !== primary && !column.hideOnMobile);

  if (loading && rows.length === 0) {
    return (
      <div className="py-10 flex justify-center text-muted-foreground">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }
  if (rows.length === 0) return <p className="py-10 text-center text-sm text-muted-foreground">{emptyText}</p>;

  return (
    <>
      <ul className="md:hidden divide-y divide-border/50">
        {rows.map((row) => (
          <li key={getId(row)}>
            <div
              role={onRowClick ? "button" : undefined}
              tabIndex={onRowClick ? 0 : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onKeyDown={onRowClick ? (event) => (event.key === "Enter" || event.key === " ") && (event.preventDefault(), onRowClick(row)) : undefined}
              className={cn("px-4 py-3 space-y-2", onRowClick && "cursor-pointer active:bg-muted/50 hover:bg-muted/30 transition-colors")}
            >
              <div className="min-w-0 font-medium text-foreground break-words">{primary.cell(row)}</div>
              {details.length > 0 && (
                <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3 gap-y-1 text-sm">
                  {details.map((column) => (
                    <div key={column.id} className="contents">
                      <dt className="text-muted-foreground">{column.header}</dt>
                      <dd className="min-w-0 break-words text-foreground">{column.cell(row)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </li>
        ))}
      </ul>

      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((column) => (
                <TableHead key={column.id} className={cn(column.align === "right" && "text-right", column.className)}>{column.header}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={getId(row)} className={cn(onRowClick && "cursor-pointer")} onClick={onRowClick ? () => onRowClick(row) : undefined}>
                {columns.map((column) => (
                  <TableCell key={column.id} className={cn(column.align === "right" && "text-right tabular-nums", column.className)}>{column.cell(row)}</TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
