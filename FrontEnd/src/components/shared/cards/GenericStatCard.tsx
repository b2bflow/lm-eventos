import { LucideIcon, TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

interface GenericStatCardProps {
  title: string;
  value: string | number;
  subtext?: string;
  icon: LucideIcon;
  variant?: "default" | "primary" | "destructive" | "accent";
  isLoading?: boolean;
  trend?: "up" | "down" | "neutral";
  onClick?: () => void;
  className?: string;
}

const VARIANTS = {
  default: {
    bgIcon: "bg-secondary/50",
    iconColor: "text-foreground",
    borderIcon: "border-border",
    gradient: "from-secondary/5 to-transparent"
  },
  primary: {
    bgIcon: "bg-primary/10",
    iconColor: "text-primary",
    borderIcon: "border-primary/20",
    gradient: "from-primary/10 to-transparent"
  },
  destructive: {
    bgIcon: "bg-destructive/10",
    iconColor: "text-destructive",
    borderIcon: "border-destructive/20",
    gradient: "from-destructive/10 to-transparent"
  },
  accent: {
    bgIcon: "bg-accent/10",
    iconColor: "text-accent",
    borderIcon: "border-accent/20",
    gradient: "from-accent/10 to-transparent"
  }
};

export function GenericStatCard({
  title,
  value,
  subtext,
  icon: Icon,
  variant = "default",
  isLoading = false,
  trend,
  onClick,
  className
}: GenericStatCardProps) {
  const styles = VARIANTS[variant];

  return (
    <div 
      onClick={onClick}
      className={cn(
        "glass rounded-2xl p-6 relative overflow-hidden group transition-all duration-300",
        onClick && "cursor-pointer hover:border-primary/30 active:scale-[0.98]",
        className
      )}
    >
      {/* Background Decorativo */}
      <div className={cn("absolute top-0 right-0 w-32 h-32 bg-gradient-to-br rounded-bl-full opacity-50", styles.gradient)} />
      
      <div className="flex items-start justify-between relative z-10">
        <div className="space-y-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </h3>
          <div className={cn(
            "w-12 h-12 rounded-xl flex items-center justify-center border transition-colors",
            styles.bgIcon, styles.borderIcon
          )}>
            <Icon className={cn("w-6 h-6", styles.iconColor)} />
          </div>
        </div>

        <div className="text-right space-y-1">
          {trend && (
            <div className="flex justify-end">
              {trend === "up" ? (
                <TrendingUp className={cn("w-4 h-4 opacity-50", styles.iconColor)} />
              ) : trend === "down" ? (
                <TrendingDown className={cn("w-4 h-4 opacity-50", styles.iconColor)} />
              ) : null}
            </div>
          )}
          
          <div className="flex items-center gap-2 justify-end">
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <span className="text-3xl font-bold text-foreground tracking-tight">
                {value}
              </span>
            )}
          </div>
          
          {subtext && (
            <p className="text-xs text-muted-foreground">{subtext}</p>
          )}
        </div>
      </div>
    </div>
  );
}