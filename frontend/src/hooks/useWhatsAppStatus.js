import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

/**
 * {enabled, connected} — WhatsApp buttons render only when the administrator has
 * switched the feature on AND the hospital's WhatsApp is linked.
 */
export default function useWhatsAppStatus() {
  const { data } = useQuery({
    queryKey: ['whatsapp-status'],
    queryFn: async () => (await axios.get('/api/whatsapp/status')).data,
    staleTime: 30_000,
    retry: false,
  });
  return { enabled: !!data?.enabled, connected: !!data?.connected, available: !!(data?.enabled && data?.connected) };
}
