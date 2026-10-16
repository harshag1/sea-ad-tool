use std::slice;

unsafe fn filter<T: Copy>(
    rows: usize,
    source_columns: usize,
    pointers: *const i64,
    indices: *const i64,
    values: *const T,
    mapping: *const i64,
    output_pointers: *mut i64,
    output_indices: *mut i64,
    output_values: *mut T,
) -> i64 {
    let pointers = slice::from_raw_parts(pointers, rows + 1);
    let total = pointers[rows] as usize;
    let indices = slice::from_raw_parts(indices, total);
    let values = slice::from_raw_parts(values, total);
    let mapping = slice::from_raw_parts(mapping, source_columns);
    let output_pointers = slice::from_raw_parts_mut(output_pointers, rows + 1);
    let output_indices = slice::from_raw_parts_mut(output_indices, total);
    let output_values = slice::from_raw_parts_mut(output_values, total);
    let mut written = 0;
    output_pointers[0] = 0;
    for row in 0..rows {
        for position in pointers[row] as usize..pointers[row + 1] as usize {
            let column = indices[position] as usize;
            if column >= source_columns {
                return -1;
            }
            let selected = mapping[column];
            if selected >= 0 {
                output_indices[written] = selected;
                output_values[written] = values[position];
                written += 1;
            }
        }
        output_pointers[row + 1] = written as i64;
    }
    written as i64
}

macro_rules! export_filter {
    ($name:ident, $value:ty) => {
        #[no_mangle]
        pub unsafe extern "C" fn $name(
            rows: usize,
            source_columns: usize,
            pointers: *const i64,
            indices: *const i64,
            values: *const $value,
            mapping: *const i64,
            output_pointers: *mut i64,
            output_indices: *mut i64,
            output_values: *mut $value,
        ) -> i64 {
            filter(rows, source_columns, pointers, indices, values, mapping, output_pointers, output_indices, output_values)
        }
    };
}

export_filter!(filter_f32, f32);
export_filter!(filter_f64, f64);
export_filter!(filter_i32, i32);
export_filter!(filter_i64, i64);
export_filter!(filter_u32, u32);
export_filter!(filter_u64, u64);
