import { createContext, useContext, useState, ReactNode } from "react";
import { DateRange } from "react-day-picker";

interface DateFilterContextType {
  dateRange: DateRange | undefined;
  setDateRange: (range: DateRange | undefined) => void;
}

const DateFilterContext = createContext<DateFilterContextType | undefined>(undefined);

export function DateFilterProvider({ children }: { children: ReactNode }) {
  // Inicializa sem nenhuma data forçada, permitindo que o backend use seu padrão de 30 dias
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);

  return (
    <DateFilterContext.Provider value={{ dateRange, setDateRange }}>
      {children}
    </DateFilterContext.Provider>
  );
}

export function useDateFilter() {
  const context = useContext(DateFilterContext);
  if (!context) {
    throw new Error("useDateFilter must be used within a DateFilterProvider");
  }
  return context;
}