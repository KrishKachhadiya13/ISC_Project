import { useQuery } from '@tanstack/react-query';

import { api } from './client';

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 });
}

export function useModels() {
  return useQuery({ queryKey: ['models'], queryFn: api.models });
}
