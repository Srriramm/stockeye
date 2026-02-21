/**
 * Browser Notifications Utility
 * Handles push notifications for stock alerts
 */

/**
 * Request permission to show browser notifications
 * @returns {Promise<boolean>} True if permission granted
 */
export const requestNotificationPermission = async () => {
  if (!("Notification" in window)) {
    console.log("Browser doesn't support notifications");
    return false;
  }

  if (Notification.permission === "granted") {
    return true;
  }

  if (Notification.permission !== "denied") {
    const permission = await Notification.requestPermission();
    return permission === "granted";
  }

  return false;
};

/**
 * Show a browser notification
 * @param {string} title - Notification title
 * @param {object} options - Notification options
 */
export const showNotification = (title, options = {}) => {
  if (Notification.permission === "granted") {
    const notification = new Notification(title, {
      icon: '/vite.svg',
      badge: '/vite.svg',
      requireInteraction: false,
      timestamp: Date.now(),
      ...options
    });

    // Auto-close after 10 seconds
    setTimeout(() => notification.close(), 10000);

    // Handle click - focus window
    notification.onclick = (event) => {
      event.preventDefault();
      window.focus();
      notification.close();
    };

    return notification;
  } else {
    console.log("Notification permission not granted");
  }
};

/**
 * Show a stock alert notification
 * @param {object} alert - Alert object with ticker, message, type
 */
export const showStockAlert = (alert) => {
  const title = `Stock Alert: ${alert.ticker}`;
  const body = alert.message;

  const options = {
    body,
    tag: `alert-${alert.id}`,
    icon: '/vite.svg',
    badge: '/vite.svg',
    requireInteraction: alert.type === 'price_alert',
    data: alert,
    actions: [
      { action: 'view', title: 'View Details' },
      { action: 'dismiss', title: 'Dismiss' }
    ]
  };

  return showNotification(title, options);
};

/**
 * Show a price change notification
 * @param {string} ticker - Stock ticker
 * @param {number} changePercent - Percentage change
 * @param {number} currentPrice - Current price
 */
export const showPriceChangeNotification = (ticker, changePercent, currentPrice) => {
  const isPositive = changePercent >= 0;
  const emoji = isPositive ? '📈' : '📉';
  const title = `${emoji} ${ticker} ${isPositive ? 'Up' : 'Down'} ${Math.abs(changePercent).toFixed(2)}%`;
  const body = `Current Price: ₹${currentPrice.toFixed(2)}`;

  return showNotification(title, {
    body,
    tag: `price-${ticker}`,
    requireInteraction: Math.abs(changePercent) >= 5  // Require interaction for 5%+ moves
  });
};

/**
 * Check if notifications are supported and enabled
 * @returns {boolean}
 */
export const areNotificationsEnabled = () => {
  return "Notification" in window && Notification.permission === "granted";
};
