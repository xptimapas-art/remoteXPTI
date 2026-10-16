import L from 'leaflet';

if (typeof window !== 'undefined') {
  (window as any).L = L;
}
