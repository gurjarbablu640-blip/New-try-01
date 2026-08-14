import React, {
  useState,
} from "react";

import { API_BASE } from "../config";

export default function AddOrderModal({

  open,
  onClose,
  onSuccess,
}) {

  const [loading, setLoading] =
    useState(false);

  const [form, setForm] =
    useState({

      company_name: "",

      order_value: "",

      order_status:
        "Order Received",

      billing_status:
        "Pending",

      payment_status:
        "Pending",

      remarks: "",
    });

  // ============================================================
  // HANDLE CHANGE
  // ============================================================

  const handleChange = (e) => {

    setForm({

      ...form,

      [e.target.name]:
        e.target.value,
    });
  };

  // ============================================================
  // SAVE ORDER
  // ============================================================

  const saveOrder = async () => {

    try {

      setLoading(true);

      const response = await fetch(

        `${API_BASE}/orders/add`,

        {

          method: "POST",

          headers: {

            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({

            ...form,

            order_value:
              parseFloat(
                form.order_value
              ),
          }),
        }
      );

      const data =
        await response.json();

      if (data.success) {

        alert(
          "Order added successfully"
        );

        onSuccess();

        onClose();

      } else {

        alert(
          "Failed to save order"
        );
      }

    } catch (error) {

      console.error(error);

      alert(
        "Server Error"
      );

    } finally {

      setLoading(false);
    }
  };

  // ============================================================
  // HIDE
  // ============================================================

  if (!open) return null;

  // ============================================================
  // UI
  // ============================================================

  return (

    <div
      className="
        fixed
        inset-0
        bg-black/40
        flex
        items-center
        justify-center
        z-50
      "
    >

      <div
        className="
          bg-white
          rounded-xl
          shadow-xl
          w-full
          max-w-2xl
          p-6
        "
      >

        {/* HEADER */}

        <div
          className="
            flex
            items-center
            justify-between
            mb-6
          "
        >

          <h2
            className="
              text-2xl
              font-bold
            "
          >
            Add Order
          </h2>

          <button
            onClick={onClose}
            className="text-gray-500"
          >
            ✕
          </button>

        </div>

        {/* FORM */}

        <div className="space-y-4">

          <input
            type="text"
            name="company_name"
            placeholder="Company Name"
            value={form.company_name}
            onChange={handleChange}
            className="
              w-full
              border
              rounded-lg
              px-4
              py-3
            "
          />

          <input
            type="number"
            name="order_value"
            placeholder="Order Value"
            value={form.order_value}
            onChange={handleChange}
            className="
              w-full
              border
              rounded-lg
              px-4
              py-3
            "
          />

          <textarea
            name="remarks"
            placeholder="Remarks"
            value={form.remarks}
            onChange={handleChange}
            rows={4}
            className="
              w-full
              border
              rounded-lg
              px-4
              py-3
            "
          />

        </div>

        {/* FOOTER */}

        <div
          className="
            flex
            justify-end
            gap-3
            mt-6
          "
        >

          <button
            onClick={onClose}
            className="
              px-4
              py-2
              border
              rounded-lg
            "
          >
            Cancel
          </button>

          <button
            onClick={saveOrder}
            disabled={loading}
            className="
              bg-blue-600
              text-white
              px-4
              py-2
              rounded-lg
            "
          >
            {loading
              ? "Saving..."
              : "Save Order"}
          </button>

        </div>

      </div>

    </div>
  );
}