import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useJobs() {
  return useQuery({ queryKey: ["jobs"], queryFn: api.listJobs });
}
