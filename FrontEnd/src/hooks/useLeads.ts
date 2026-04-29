import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import api from "@/services/api"; 

export interface Lead {
  id: string;
  quote_id?: string;
  customer?: string;
  customer_id?: string;
  name: string;
  phone: string;
  customer_state_now: string;
  actual_status?: string;
  customer_custom_tag?: string | null;
  celebration_type?: string | null;
  event_title?: string | null;
  event_date?: string | null;
  guest_count?: number;
  quoted_amount?: number;
  contract_value?: number;
  venue?: string | null;
  notes?: string | null;
  proposal_sent_at?: string | null;
  last_interaction_at?: string | null;
  next_step?: string | null;
  created_at: string;
  updated_at: string;
}

interface LeadsResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Lead[];
}

export const useLeads = () => {
  const [page, setPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const { data, isLoading, isError, refetch } = useQuery<LeadsResponse>({
    queryKey: ["leads", page, searchTerm, statusFilter],
    queryFn: async () => {
      const response = await api.get("/crm/quotes/", {
        params: {
          page,
          search: searchTerm || undefined,
          tag: statusFilter === "all" ? undefined : statusFilter,
        },
      });
      return response.data;
    },
    placeholderData: keepPreviousData,
    refetchInterval: 4000,
  });

  return {
    leads: data?.results || [],
    totalPages: data ? Math.ceil(data.count / 10) : 1,
    isLoading,
    isError,
    page,
    setPage,
    searchTerm,
    setSearchTerm,
    statusFilter,      
    setStatusFilter,   
    refetch,
  };
};
