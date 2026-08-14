import React, {
  useEffect,
  useState,
} from "react";

import { API_BASE } from "../config";

export default function OrdersPanel() {

  const [orders, setOrders] =
    useState([]);

  const [summary, setSummary] =
    useState({

      total_orders: 0,

      total_revenue: 0,
    });

  const [loading, setLoading] =
    useState(true);

  // ============================================================
  // FETCH ORDERS
  // ============================================================

  const fetchOrders = async () => {

    try {

      const response = await fetch(
        `${API_BASE}/orders/`
      );

      const data =
        await response.json();

      setOrders(
        data.results || []
      );

      setSummary({

        total_orders:
          data.total_orders || 0,

        total_revenue:
          data.total_revenue || 0,
      });

    } catch (error) {

      console.error(error);

    } finally {

      setLoading(false);
    }
  };

  // ============================================================
  // LOAD
  // ============================================================

  useEffect(() => {

    fetchOrders();

  }, []);

  // ============================================================
  // UI
  // ============================================================

  return (

    <div
      className="
        bg-white
        rounded-xl
        shadow
        p-6
      "
    >

      {/* ====================================================== */}
      {/* HEADER */}
      {/* ====================================================== */}

      <div
        className="
          flex
          items-center
          justify-between
          mb-6
        "
      >

        <div>

          <h2
            className="
              text-2xl
              font-bold
              text-gray-800
            "
          >
            Orders Dashboard
          </h2>

          <p
            className="
              text-sm
              text-gray-500
            "
          >
            Revenue & order tracking
          </p>

        </div>

      </div>

      {/* ====================================================== */}
      {/* SUMMARY CARDS */}
      {/* ====================================================== */}

      <div
        className="
          grid
          grid-cols-1
          md:grid-cols-2
          gap-4
          mb-6
        "
      >

        {/* TOTAL ORDERS */}

        <div
          className="
            bg-blue-50
            border
            rounded-xl
            p-5
          "
        >

          <div className="text-sm text-gray-500">
            Total Orders
          </div>

          <div
            className="
              text-3xl
              font-bold
              text-blue-700
              mt-2
            "
          >
            {summary.total_orders}
          </div>

        </div>

        {/* REVENUE */}

        <div
          className="
            bg-green-50
            border
            rounded-xl
            p-5
          "
        >

          <div className="text-sm text-gray-500">
            Total Revenue
          </div>

          <div
            className="
              text-3xl
              font-bold
              text-green-700
              mt-2
            "
          >
            ₹
            {summary.total_revenue.toLocaleString()}
          </div>

        </div>

      </div>

      {/* ====================================================== */}
      {/* TABLE */}
      {/* ====================================================== */}

      {loading ? (

        <div className="py-10 text-center">
          Loading orders...
        </div>

      ) : (

        <div className="overflow-x-auto">

          <table className="min-w-full border">

            <thead className="bg-gray-100">

              <tr>

                <th className="p-3 text-left">
                  Company
                </th>

                <th className="p-3 text-left">
                  Value
                </th>

                <th className="p-3 text-left">
                  Order Status
                </th>

                <th className="p-3 text-left">
                  Billing
                </th>

                <th className="p-3 text-left">
                  Payment
                </th>

                <th className="p-3 text-left">
                  Remarks
                </th>

              </tr>

            </thead>

            <tbody>

              {orders.map((item) => (

                <tr
                  key={item.id}
                  className="
                    border-t
                    hover:bg-gray-50
                  "
                >

                  <td className="p-3 font-medium">
                    {item.company_name}
                  </td>

                  <td className="p-3">
                    ₹
                    {item.order_value.toLocaleString()}
                  </td>

                  <td className="p-3">
                    {item.order_status}
                  </td>

                  <td className="p-3">
                    {item.billing_status}
                  </td>

                  <td className="p-3">

                    <span
                      className="
                        px-2
                        py-1
                        rounded-full
                        text-xs
                        bg-yellow-100
                        text-yellow-700
                      "
                    >
                      {item.payment_status}
                    </span>

                  </td>

                  <td className="p-3">
                    {item.remarks}
                  </td>

                </tr>

              ))}

            </tbody>

          </table>

        </div>

      )}

    </div>
  );
}