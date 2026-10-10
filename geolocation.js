// Browser-managed coordinates stay in memory and are never persisted here.
export function requestCurrentPosition(geolocation, onSuccess, onError, onRetry = () => {}) {
  const attempt = (retry) => {
    geolocation.getCurrentPosition(onSuccess, error => {
      if (!retry && (error.code === 2 || error.code === 3)) {
        onRetry();
        attempt(true);
      } else {
        onError(error);
      }
    }, {enableHighAccuracy: retry, timeout: 15000, maximumAge: retry ? 0 : 60000});
  };
  attempt(false);
}
