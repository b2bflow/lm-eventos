import { useState, useEffect } from "react";
import { format, differenceInDays, parse, isValid, isAfter } from "date-fns";
import { ptBR } from "date-fns/locale";
import { CalendarDays, ChevronDown, Eraser } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useDateFilter } from "@/contexts/DateFilterContext";
import { toast } from "sonner";

export function CalendarioCard() {
  const { dateRange, setDateRange } = useDateFilter();
  
  const [inputValueFrom, setInputValueFrom] = useState("");
  const [inputValueTo, setInputValueTo] = useState("");
  
  const [isOpenFrom, setIsOpenFrom] = useState(false);
  const [isOpenTo, setIsOpenTo] = useState(false);
  
  const [monthFrom, setMonthFrom] = useState<Date>(new Date());
  const [monthTo, setMonthTo] = useState<Date>(new Date());

  useEffect(() => {
    if (dateRange?.from) {
      setInputValueFrom(format(dateRange.from, "dd/MM/yyyy"));
    } else {
      setInputValueFrom("");
    }
    
    if (dateRange?.to) {
      setInputValueTo(format(dateRange.to, "dd/MM/yyyy"));
    } else {
      setInputValueTo("");
    }
  }, [dateRange]);

  const updateRange = (newFrom: Date | undefined, newTo: Date | undefined) => {
    if (newFrom && newTo) {
      if (isAfter(newFrom, newTo)) {
        toast.error("A data inicial não pode ser depois da data final.");
        return false;
      }
      if (Math.abs(differenceInDays(newTo, newFrom)) > 365) {
        toast.error("O período máximo permitido é de 1 ano (365 dias).");
        return false;
      }
    }
    setDateRange({ from: newFrom, to: newTo });
    return true;
  };

  const handleSelectFrom = (date: Date | undefined) => {
    if (updateRange(date, dateRange?.to)) {
      setIsOpenFrom(false);
    }
  };

  const handleSelectTo = (date: Date | undefined) => {
    if (updateRange(dateRange?.from, date)) {
      setIsOpenTo(false);
    }
  };

  const handleBlurFrom = () => {
    if (!inputValueFrom.trim()) {
      updateRange(undefined, dateRange?.to);
      return;
    }
    const parsed = parse(inputValueFrom, "dd/MM/yyyy", new Date());
    if (isValid(parsed)) {
      updateRange(parsed, dateRange?.to);
    } else {
      toast.error("Data inicial inválida. Use DD/MM/AAAA");
      setInputValueFrom(dateRange?.from ? format(dateRange.from, "dd/MM/yyyy") : "");
    }
  };

  const handleBlurTo = () => {
    if (!inputValueTo.trim()) {
      updateRange(dateRange?.from, undefined);
      return;
    }
    const parsed = parse(inputValueTo, "dd/MM/yyyy", new Date());
    if (isValid(parsed)) {
      updateRange(dateRange?.from, parsed);
    } else {
      toast.error("Data final inválida. Use DD/MM/AAAA");
      setInputValueTo(dateRange?.to ? format(dateRange.to, "dd/MM/yyyy") : "");
    }
  };

  const handleReset = () => {
    setDateRange(undefined);
    toast.success("Filtro limpo! Exibindo os últimos 30 dias.");
  };

  return (
    <div className="glass rounded-2xl p-6 card-hover h-full relative overflow-hidden group">
      <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-primary/10 to-transparent rounded-bl-full pointer-events-none" />
      
      <div className="flex items-center justify-between mb-5 relative z-10">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Período de Análise
        </h3>
        <div className="w-8 h-8 rounded-lg bg-primary/5 flex items-center justify-center border border-primary/10">
          <CalendarDays className="w-4 h-4 text-primary/80" />
        </div>
      </div>
      
      <div className="relative z-10 grid grid-cols-2 gap-3">
        {/* Data Inicial */}
        <div className={cn(
          "w-full flex items-center justify-between bg-background/40 border border-border/40 hover:border-primary/30 transition-all duration-300 rounded-lg focus-within:ring-1 focus-within:ring-primary/20 focus-within:border-primary/50",
          !dateRange?.from && "text-muted-foreground"
        )}>
          <div className="flex flex-col flex-1 items-start text-left py-2 px-3 overflow-hidden">
            <span className="text-[10px] text-muted-foreground/70 font-medium uppercase tracking-wide mb-0.5">
              De
            </span>
            <input
              type="text"
              value={inputValueFrom}
              onChange={(e) => setInputValueFrom(e.target.value)}
              onBlur={handleBlurFrom}
              onKeyDown={(e) => e.key === 'Enter' && handleBlurFrom()}
              className="w-full bg-transparent text-xs font-medium text-foreground outline-none placeholder:font-normal placeholder:text-muted-foreground/40 truncate"
              placeholder="Padrão"
            />
          </div>

          <Popover open={isOpenFrom} onOpenChange={(open) => { setIsOpenFrom(open); if(open) setMonthFrom(dateRange?.from || new Date()); }}>
            <PopoverTrigger asChild>
              <button className="h-full py-3 px-2.5 flex items-center justify-center hover:bg-muted/50 transition-colors border-l border-border/40 text-muted-foreground hover:text-foreground outline-none">
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0 glass-strong border-border/50" align="start">
              <Calendar
                mode="single"
                month={monthFrom}
                onMonthChange={setMonthFrom}
                defaultMonth={monthFrom}
                selected={dateRange?.from}
                onSelect={handleSelectFrom}
                locale={ptBR}
                className="p-3 pointer-events-auto"
              />
            </PopoverContent>
          </Popover>
        </div>

        {/* Data Final */}
        <div className={cn(
          "w-full flex items-center justify-between bg-background/40 border border-border/40 hover:border-primary/30 transition-all duration-300 rounded-lg focus-within:ring-1 focus-within:ring-primary/20 focus-within:border-primary/50",
          !dateRange?.to && "text-muted-foreground"
        )}>
          <div className="flex flex-col flex-1 items-start text-left py-2 px-3 overflow-hidden">
            <span className="text-[10px] text-muted-foreground/70 font-medium uppercase tracking-wide mb-0.5">
              Até
            </span>
            <input
              type="text"
              value={inputValueTo}
              onChange={(e) => setInputValueTo(e.target.value)}
              onBlur={handleBlurTo}
              onKeyDown={(e) => e.key === 'Enter' && handleBlurTo()}
              className="w-full bg-transparent text-xs font-medium text-foreground outline-none placeholder:font-normal placeholder:text-muted-foreground/40 truncate"
              placeholder="30 Dias"
            />
          </div>

          <Popover open={isOpenTo} onOpenChange={(open) => { setIsOpenTo(open); if(open) setMonthTo(dateRange?.to || new Date()); }}>
            <PopoverTrigger asChild>
              <button className="h-full py-3 px-2.5 flex items-center justify-center hover:bg-muted/50 transition-colors border-l border-border/40 text-muted-foreground hover:text-foreground outline-none">
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0 glass-strong border-border/50" align="end">
              <Calendar
                mode="single"
                month={monthTo}
                onMonthChange={setMonthTo}
                defaultMonth={monthTo}
                selected={dateRange?.to}
                onSelect={handleSelectTo}
                locale={ptBR}
                className="p-3 pointer-events-auto"
              />
            </PopoverContent>
          </Popover>
        </div>
      </div>
      
      <div className="mt-5 border-t border-border/20 pt-4 relative z-10">
        <Button
          variant="ghost"
          size="sm"
          className="w-full text-xs font-medium text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
          onClick={handleReset}
        >
          <Eraser className="w-3.5 h-3.5 mr-2" />
          Limpar Filtro
        </Button>
      </div>
    </div>
  );
}