import React, { useState } from "react";

import { API_BASE } from "../config";

export default function AddActivityModal({

  open,

  onClose,

  onSuccess,
}) {

  const [form, setForm] = useState({

    company_id: "",

    activity_type: "Call",

    status: "Interested",

    remarks: "",

    contact_person: "",

    division: "",

    phone: "",

    email: "",

    next_followup_date: "",
  });

  const [loading, setLoading] =
    useState(false);

  // ============================================================
  // CHANGE
  // ============================================================

  const handleChange = (e) => {

    setForm({

      ...form,

      [e.target.name]:
        e.target.value,
    });
  };

  // ============================================================
  // SUBMIT
  // ============================================================

  const handleSubmit = async () => {

    try {

      setLoading(true);

      const response = await fetch(
        `${API_BASE}/activities/add`,
        {

          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({

            ...form,

            company_id: Number(
              form.company_id
            ),
          }),
        }
      );

      const data =
        await response.json();

      console.log(data);

      if (
        response.ok &&
        data.success
      ) {

        alert(
          "Activity Added Successfully"
        );

        onSuccess();

        onClose();

      } else {

        alert(
          JSON.stringify(data)
        );
      }

    } catch (error) {

      console.error(error);

      alert(
        error.message
      );

    } finally {

      setLoading(false);
    }
  };

  // ============================================================
  // CLOSE
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
        bg-black/50
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
            Add CRM Activity
          </h2>

          <button
            onClick={onClose}
            className="
              text-gray-500
              hover:text-black
            "
          >
            ✕
          </button>

        </div>

        {/* FORM */}

        <div
          className="
            grid
            grid-cols-2
            gap-4
          "
        >

          <input
            type="number"
            name="company_id"
            placeholder="Company ID"
            value={form.company_id}
            onChange={handleChange}
            className="border p-3 rounded"
          />

          <select
            name="activity_type"
            value={form.activity_type}
            onChange={handleChange}
            className="border p-3 rounded"
          >

            <option>Call</option>

            <option>Email</option>

            <option>WhatsApp</option>

            <option>Follow-up</option>

          </select>

          <input
            name="contact_person"
            placeholder="Contact Person"
            value={form.contact_person}
            onChange={handleChange}
            className="border p-3 rounded"
          />

          <input
            name="division"
            placeholder="Division"
            value={form.division}
            onChange={handleChange}
            className="border p-3 rounded"
          />

          <input
            name="phone"
            placeholder="Phone"
            value={form.phone}
            onChange={handleChange}
            className="border p-3 rounded"
          />

          <input
            name="email"
            placeholder="Email"
            value={form.email}
            onChange={handleChange}
            className="border p-3 rounded"
          />

          <select
            name="status"
            value={form.status}
            onChange={handleChange}
            className="border p-3 rounded"
          >

            <option>Interested</option>

            <option>Follow-up</option>

            <option>No Response</option>

            <option>Quotation Sent</option>

            <option>Closed</option>

          </select>

          <input
            type="datetime-local"
            name="next_followup_date"
            value={form.next_followup_date}
            onChange={handleChange}
            className="border p-3 rounded"
          />

        </div>

        {/* REMARKS */}

        <textarea
          name="remarks"
          placeholder="Remarks"
          value={form.remarks}
          onChange={handleChange}
          rows={4}
          className="
            border
            p-3
            rounded
            w-full
            mt-4
          "
        />

        {/* ACTIONS */}

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
              rounded
            "
          >
            Cancel
          </button>

          <button
            onClick={handleSubmit}
            disabled={loading}
            className="
              bg-blue-600
              text-white
              px-4
              py-2
              rounded
              hover:bg-blue-700
            "
          >

            {loading
              ? "Saving..."
              : "Save Activity"}

          </button>

        </div>

      </div>

    </div>
  );
}