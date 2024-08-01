def _get_mtf_data(self, sfr_data, oversampling_rate):
        mtf_data = [0] * int(len(sfr_data) / 2 / (oversampling_rate * 0.5))
        mtf50 = 0
        for idx in range(len(mtf_data)):
            freq = idx / (len(mtf_data) - 1)
            if freq == 0:
                mtf_data[idx] = sfr_data[idx]
            else:
                mtf_data[idx] = sfr_data[idx] * (np.pi * freq * 2 / oversampling_rate) / np.sin(np.pi * freq * 2 / oversampling_rate)
            if idx > 0 and mtf_data[idx] < 0.5 and mtf_data[idx - 1] >= 0.5:
                mtf50 = (idx - 1 + (0.5 - mtf_data[idx]) / (mtf_data[idx - 1] - mtf_data[idx])) / (len(mtf_data) - 1)
                break
        return mtf_data, mtf50, 0