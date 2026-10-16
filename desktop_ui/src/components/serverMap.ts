export function hasServerLocation(server: { latitude?: number | null; longitude?: number | null }) {
  return typeof server.latitude === 'number' && Number.isFinite(server.latitude)
    && server.latitude >= -90 && server.latitude <= 90
    && typeof server.longitude === 'number' && Number.isFinite(server.longitude)
    && server.longitude >= -180 && server.longitude <= 180;
}
